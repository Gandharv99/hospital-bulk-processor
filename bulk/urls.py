from django.urls import path
from .views import HospitalBulkUploadView
from .views import health_check

app_name = 'bulk'

urlpatterns = [
    path('hospitals/bulk', HospitalBulkUploadView.as_view(), name='bulk-upload'),
    path('health', health_check, name='health-check'),
]