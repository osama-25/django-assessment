from django.urls import path
from . import views

urlpatterns = [
    path('route_optimization/', views.route_optimize),
]
