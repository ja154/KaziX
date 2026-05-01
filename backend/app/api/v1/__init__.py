"""
app/api/v1/__init__.py
──────────────────────
Aggregates all v1 route modules into a single router.
"""

from fastapi import APIRouter

from app.api.v1 import admin, applications, auth, bookings, dashboard, jobs, messages, mpesa, notifications, profiles

router = APIRouter()

router.include_router(auth.router,          prefix="/auth",         tags=["auth"])
router.include_router(profiles.router,      prefix="/profiles",     tags=["profiles"])
router.include_router(dashboard.router,     prefix="/dashboard",    tags=["dashboard"])
router.include_router(jobs.router,          prefix="/jobs",         tags=["jobs"])
router.include_router(applications.router,  prefix="/applications", tags=["applications"])
router.include_router(bookings.router,      prefix="/bookings",     tags=["bookings"])
router.include_router(messages.router,      prefix="/messages",     tags=["messages"])
router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
router.include_router(mpesa.router,         prefix="/mpesa",        tags=["mpesa"])
router.include_router(admin.router,         prefix="/admin",        tags=["admin"])
