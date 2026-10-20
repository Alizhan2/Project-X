"""Private download endpoints. Calendar files are snapshots, not subscriptions."""
from datetime import timezone as dt_timezone
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.core.throttling import throttle
from apps.core.i18n import tr, language, place_name
from .models import Booking
from .travel import travel_plan, upcoming_plan
from .views import Conflict, _own_booking


def private(response):
    response["Cache-Control"] = "private, no-store"
    return response


@extend_schema(responses={200: dict})
@api_view(["GET"])
def upcoming(request):
    return private(Response({"journey": upcoming_plan(request.user)}))


def text(value):
    return str(value).replace("\\", "\\\\").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def folded(line):
    """RFC 5545: at most 75 octets per physical line, without splitting UTF-8."""
    lines, current = [], ""
    for char in line:
        if len((current + char).encode("utf-8")) > 75:
            lines.append(current)
            current = " "
        current += char
    return "\r\n".join([*lines, current])


def stamp(value):
    return value.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def calendar_bytes(plan):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Doedu//Journey plan//" + language().upper(), "CALSCALE:GREGORIAN"]
    for leg in plan["legs"]:
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{plan['reference']}-{leg['sequence']}@doedu.invalid",
            f"DTSTAMP:{stamp(plan['generated_at'])}",
            f"DTSTART:{stamp(leg['departs_at'])}",
            f"DTEND:{stamp(leg['arrives_at'])}",
            "SUMMARY:" + text(f"[DEMO] {tr(leg['mode'])} {leg['route_code']}: {place_name(leg['from'])} → {place_name(leg['to'])}"),
            "LOCATION:" + text(place_name(leg["from"])),
            "DESCRIPTION:" + text(
                f"Doedu {plan['reference']}. {leg['operator']}.\n"
                + tr("Destination: {0}.", place_name(leg['to'])) + "\n"
                + tr("Simulated journey. Not a valid travel ticket.") + "\n"
                + tr("Downloaded timetable snapshot; changes and cancellations do not update automatically. Check Doedu before travelling.")
            ),
            "STATUS:CONFIRMED", "TRANSP:OPAQUE", "CLASS:PRIVATE", "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    return ("\r\n".join(folded(line) for line in lines) + "\r\n").encode("utf-8")


def pdf_bytes(plan, booking):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether

    if "DoeduSans" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("DoeduSans", str(Path(__file__).parent / "fonts" / "DejaVuSans.ttf")))
    stream = BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=(595.28, 841.89), rightMargin=44, leftMargin=44,
                           topMargin=48, bottomMargin=55, title=f"Doedu / {booking.reference}")
    normal = ParagraphStyle("body", fontName="DoeduSans", fontSize=10, leading=15, textColor=colors.HexColor("#193047"), spaceAfter=8, alignment=TA_LEFT)
    title = ParagraphStyle("title", parent=normal, fontSize=25, leading=32, spaceAfter=15)
    heading = ParagraphStyle("heading", parent=normal, fontSize=13, leading=19, spaceAfter=10)
    warning = ParagraphStyle("warning", parent=normal, textColor=colors.HexColor("#8a310d"), backColor=colors.HexColor("#fff3df"), borderPadding=9, spaceBefore=8, spaceAfter=17)
    def p(value, style=normal):
        return Paragraph(escape(tr(str(value))), style)
    def local(value):
        # Numeric regional date avoids process-global locale and preserves DST offset.
        return timezone.localtime(value).strftime("%d.%m.%Y, %H:%M %Z")
    story = [
        p("DOEDU / JOURNEY PLAN", title),
        p(tr("Booking {0} · {1} passenger(s)", booking.reference, booking.passengers), heading),
        p("DEMONSTRATION - Not a valid travel ticket. All services and payments are simulated.", warning),
        p(f"Updated {local(plan['generated_at'])}. All times use Europe/Berlin."),
        p("This downloaded copy does not update automatically. Check Doedu for changes before travelling."),
    ]
    if plan["status"] == "broken":
        story.append(p("JOURNEY DISRUPTED - This route cannot currently be completed as shown. Open your booking to review replacements or cancellation.", warning))
    elif plan["status"] == "delayed":
        story.append(p("TIMETABLE CHANGED - Current estimated times are shown below.", warning))
    for index, leg in enumerate(plan["legs"]):
        section = [p(f"{index + 1}. {tr(leg['mode']).upper()} {leg['route_code']} / {leg['operator']}", heading),
                   p(f"From: {place_name(leg['from'])}"), p(f"Departure: {local(leg['departs_at'])}"),
                   p(f"To: {place_name(leg['to'])}"), p(f"Arrival: {local(leg['arrives_at'])}")]
        if leg["state"] == "unavailable":
            section.append(p("SERVICE UNAVAILABLE", warning))
        if leg["departs_at"] != leg["scheduled_departs_at"]:
            section.append(p(f"Originally booked departure: {local(leg['scheduled_departs_at'])}"))
        if index < len(plan["legs"]) - 1:
            following = plan["legs"][index + 1]
            minutes = int((following["departs_at"] - leg["arrives_at"]).total_seconds() // 60)
            section.append(p(f"Connection: {minutes} min between arrival and next departure, including walking."))
        section.append(Spacer(1, 14))
        story.append(KeepTogether(section))
    story.extend([p(f"Net paid: {booking.currency} {booking.total_amount:.2f} (simulated)."),
                  p("Progress is based on the timetable, not GPS. Passenger names and contact details are omitted from this portable copy.")])
    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("DoeduSans", 8)
        canvas.setFillColor(colors.HexColor("#526476"))
        canvas.drawString(44, 28, f"Doedu | {booking.reference} | DEMO")
        canvas.drawRightString(551, 28, tr("Page {0}", document.page))
        canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()


@extend_schema(responses={(200, "text/calendar"): OpenApiTypes.BINARY, 409: dict})
@throttle("booking")
@api_view(["GET"])
def calendar(request, reference):
    booking = _own_booking(request, reference)
    plan = export_plan(booking)
    if plan["status"] == "broken":
        raise Conflict("journey_disrupted", "Resolve the disruption before adding this journey to your calendar.")
    return download(calendar_bytes(plan), reference, "ics", "text/calendar; charset=utf-8")


@extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY, 409: dict})
@throttle("booking")
@api_view(["GET"])
def pdf(request, reference):
    booking = _own_booking(request, reference)
    plan = export_plan(booking)
    return download(pdf_bytes(plan, booking), reference, "pdf", "application/pdf")


def export_plan(booking):
    if booking.status != Booking.Status.CONFIRMED:
        raise Conflict("not_confirmed", "Only confirmed bookings can be exported.")
    plan = travel_plan(booking)
    if not plan["legs"]:
        raise Conflict("no_route", "This booking has no active route.")
    return plan


def download(content, reference, extension, content_type):
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="doedu-{reference}.{extension}"'
    response["X-Content-Type-Options"] = "nosniff"
    return private(response)
