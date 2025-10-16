from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BuildRecordViewSet

router = DefaultRouter()
router.register(r'builds', BuildRecordViewSet, basename='builds')

urlpatterns = [
    path('api/', include(router.urls)),
]
