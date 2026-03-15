from rest_framework.response import Response


def build_envelope(*, data=None, message="", error=None, url=None):
    return {
        "status": error is None,
        "message": message,
        "data": data if error is None else None,
        "error": error,
        "url": url,
    }


class APIResponse(Response):
    def __init__(
        self,
        data=None,
        message="",
        error=None,
        status=200,
        headers=None
    ):
        body = build_envelope(data=data, message=message, error=error, url=None)

        super().__init__(body, status=status, headers=headers)

    def render(self):
        renderer_context = getattr(self, 'renderer_context', None) or {}
        request = renderer_context.get('request')

        if request and isinstance(self.data, dict):
            self.data['url'] = request.path

        return super().render()
