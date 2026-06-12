from .auth_routes import router as auth_router
from .microsoft_auth_routes import router as microsoft_auth_router
from .email_routes import router as email_router
from .gmail_routes import router as gmail_router
from .intelligence_routes import router as intelligence_router
from .policy_routes import router as policy_router
from .security_routes import router as security_router
from .settings_routes import router as settings_router

# List of all routers for dynamic mounting if needed
ALL_ROUTERS = [
    auth_router,
    microsoft_auth_router,
    email_router,
    gmail_router,
    intelligence_router,
    policy_router,
    security_router,
    settings_router
]
