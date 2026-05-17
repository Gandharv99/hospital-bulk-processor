from django.urls import path
from .views import HospitalBulkUploadView
from .views import health_check
from .views import CSVValidationView

app_name = 'bulk'

urlpatterns = [
    path('hospitals/bulk', HospitalBulkUploadView.as_view(), name='bulk-upload'),
    path('health', health_check, name='health-check'),
    path('hospitals/bulk/validate', CSVValidationView.as_view(), name='bulk-validate'),
]