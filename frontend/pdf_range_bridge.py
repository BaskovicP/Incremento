"""Instance-owned PDF byte replies; file I/O stays on the task executor."""
import base64
import json

try:
    from ..backend.pdf_byte_ranges import PdfByteRangeSource
    from ..backend.pdf_reading_priority import defer_for_pdf_reading
except ImportError:
    from pdf_byte_ranges import PdfByteRangeSource
    from pdf_reading_priority import defer_for_pdf_reading

PREFIX = 'incremento_pdf_range:'


class PdfRangeBridge:
    def __init__(self, submit, reply, is_current):
        self.submit, self.reply, self.is_current = submit, reply, is_current
        self.source = None
        self.pending = 0

    def open(self, addon_dir, profile, card_id, path):
        self.close()
        if path is not None:
            self.source = PdfByteRangeSource(addon_dir, profile, card_id, path)
            defer_for_pdf_reading()
        return self.source.descriptor if self.source else None

    def close(self):
        self.source = None
        self.pending = 0

    def handle(self, message):
        if isinstance(message, str) and message.startswith((
                'incremento_pdf_nav:', 'incremento_pdf_zoom:', 'incremento_pdf_scroll:')):
            defer_for_pdf_reading()
        if not isinstance(message, str) or not message.startswith(PREFIX):
            return False
        source = self.source
        if source is None or not self.is_current(source.profile, source.card_id) or len(message) > 4096:
            return True
        try:
            data = json.loads(message[len(PREFIX):])
            if (not isinstance(data, dict) or data.get('token') != source.descriptor['token']
                    or type(data.get('cardId')) is not int or data['cardId'] != source.card_id
                    or type(data.get('requestId')) is not int or not 0 <= data['requestId'] <= 2**31):
                return True
            request_id, begin, end = data['requestId'], data.get('begin'), data.get('end')
            response = {'token': source.descriptor['token'], 'requestId': request_id, 'begin': begin}
            if self.pending >= 4:
                self.reply({**response, 'error': True})
                return True
            self.pending += 1
            defer_for_pdf_reading()

            def work():
                return base64.b64encode(source.read(begin, end)).decode('ascii')

            def done(future):
                if self.source is not source:
                    return
                self.pending -= 1
                if not self.is_current(source.profile, source.card_id):
                    return
                try:
                    result = {**response, 'data': future.result()}
                except Exception:
                    result = {**response, 'error': True}
                self.reply(result)

            try:
                self.submit(work, done)
            except Exception:
                self.pending -= 1
                self.reply({**response, 'error': True})
        except (ValueError, TypeError):
            pass
        return True
