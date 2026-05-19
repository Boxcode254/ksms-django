from asgiref.local import Local

_state = Local()


def set_current_request(request):
    _state.request = request


def get_current_request():
    return getattr(_state, "request", None)


def clear_current_request():
    if hasattr(_state, "request"):
        del _state.request


def get_client_ip(request=None):
    request = request or get_current_request()
    if request is None:
        return None

    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def get_user_agent(request=None):
    request = request or get_current_request()
    if request is None:
        return ""
    return request.META.get("HTTP_USER_AGENT", "")
