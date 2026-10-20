"""Private local mail preview files, never served over HTTP or printed to logs."""
import os
from django.core.mail.backends.filebased import EmailBackend as FileBackend


class EmailBackend(FileBackend):
    def open(self):
        if self.stream is None:
            os.chmod(self.file_path, 0o700)
            fd = os.open(self._get_filename(), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            self.stream = os.fdopen(fd, 'ab')
            return True
        return False
