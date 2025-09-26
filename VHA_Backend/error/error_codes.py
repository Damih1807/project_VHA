class ErrorCode:
    SUCCESS = 200
    CREATED = 201
    ACCEPTED = 202
    NO_CONTENT = 204

    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    METHOD_NOT_ALLOWED = 405
    CONFLICT = 409
    UNPROCESSABLE_ENTITY = 422
    TOO_MANY_REQUESTS = 429

    SERVER_ERROR = 500
    BAD_GATEWAY = 502
    SERVICE_UNAVAILABLE = 503
    GATEWAY_TIMEOUT = 504


    messages = {
        SUCCESS: "Success",
        CREATED: "Resource created successfully",
        ACCEPTED: "Request accepted",
        NO_CONTENT: "Success - no content to return",

        BAD_REQUEST: "Invalid request",
        UNAUTHORIZED: "Unauthorized or invalid token",
        FORBIDDEN: "Access denied",
        NOT_FOUND: "Resource not found",
        METHOD_NOT_ALLOWED: "HTTP method not allowed",
        CONFLICT: "Conflict or duplicate data",
        UNPROCESSABLE_ENTITY: "Unprocessable entity - validation failed",
        TOO_MANY_REQUESTS: "Too many requests - please try again later",

        SERVER_ERROR: "Internal server error",
        BAD_GATEWAY: "Invalid response from upstream server",
        SERVICE_UNAVAILABLE: "Service unavailable or under maintenance",
        GATEWAY_TIMEOUT: "Gateway timeout - server took too long to respond",
    }

    @staticmethod
    def get_message(code):
        return ErrorCode.messages.get(code, "Lỗi không xác định")
