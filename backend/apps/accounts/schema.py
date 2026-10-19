from drf_spectacular.extensions import OpenApiAuthenticationExtension


class StrictCsrfSessionAuthScheme(OpenApiAuthenticationExtension):
    target_class = "apps.accounts.views.StrictCsrfSessionAuth"
    name = "sessionAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "cookie", "name": "sessionid",
                "description": "Django session cookie. Unsafe methods also need the X-CSRFToken header (cookie `csrftoken`)."}
