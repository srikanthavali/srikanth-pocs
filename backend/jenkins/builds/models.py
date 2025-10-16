from django.db import models

class BuildRecord(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('RUNNING', 'Running'),
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
        ('STOPPED', 'Stopped'),
        ('ABORTED', 'Aborted'),
    ]

    job_name = models.CharField(max_length=255)
    build_number = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    log_path = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        unique_together = ('job_name', 'build_number')

    def __str__(self):
        return f"{self.job_name} - {self.build_number or 'Pending'}"
