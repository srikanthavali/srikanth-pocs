from rest_framework import serializers
from .models import BuildRecord

class BuildRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuildRecord
        fields = '__all__'
