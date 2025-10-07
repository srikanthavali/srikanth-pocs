from django.urls import path
from . import views

urlpatterns = [
    path('jenkins/proxy/', views.jenkins_proxy),
]
