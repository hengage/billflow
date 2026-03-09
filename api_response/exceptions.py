from rest_framework.views import exception_handler
from rest_framework.response import Response

def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        data = response.data
        request = context.get("request")
        print('Context:', context)
        print('Request:', request)
        payload = {
            "status": False,
            "message": "",
            "data": None,
            "url": request.path if request else None,
            "error": data,
        }

        # Include top-level messages if provided
        if isinstance(data, dict) and "detail" in data:
            payload["message"] = data["detail"]

        return Response(payload, status=response.status_code)

    return response
