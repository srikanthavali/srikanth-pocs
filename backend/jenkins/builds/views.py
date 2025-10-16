from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import BuildRecord
from .serializers import BuildRecordSerializer
from .tasks import start_and_poll_build, stop_build
from .storage import read_logs  # Helper to read logs from storage
import os

class BuildRecordViewSet(viewsets.ModelViewSet):
    queryset = BuildRecord.objects.all().order_by('-created_at')
    serializer_class = BuildRecordSerializer

    # ---- Trigger Start ----
    @action(detail=False, methods=["post"])
    def start(self, request):
        """
        Start a build.
        If build record exists (by job_name), use it.
        Otherwise, create a new BuildRecord first.
        """
        job_name = request.data.get("job_name")
        if not job_name:
            return Response({"detail": "job_name is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Check if there is already a pending/running build for this job
        build_record = BuildRecord.objects.filter(job_name=job_name, status__in=["PENDING", "RUNNING"]).first()
        if build_record:
            return Response({"detail": f"Build already exists with status {build_record.status}", "id": build_record.id}, status=status.HTTP_200_OK)

        # Create a new BuildRecord
        build_record = BuildRecord.objects.create(
            job_name=job_name,
            status="PENDING",
        )

        # Trigger the build via Dramatiq
        start_and_poll_build.send(build_record.id)

        serializer = BuildRecordSerializer(build_record)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # ---- Stop Build ----
    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        build_record = self.get_object()
        if build_record.status not in ["RUNNING", "PENDING"]:
            return Response({"detail": f"Cannot stop build in status {build_record.status}"}, status=status.HTTP_400_BAD_REQUEST)

        # Trigger stop task
        stop_build.send(build_record.id)
        return Response({"detail": "Stop triggered"}, status=status.HTTP_200_OK)

    # ---- Check Status ----
    @action(detail=True, methods=["get"])
    def status(self, request, pk=None):
        build_record = self.get_object()
        return Response({
            "id": build_record.id,
            "job_name": build_record.job_name,
            "build_number": build_record.build_number,
            "status": build_record.status,
            "start_time": build_record.start_time,
            "end_time": build_record.end_time,
        })

    # ---- Fetch logs ----
    @action(detail=True, methods=["get"])
    def logs(self, request, pk=None):
        build_record = self.get_object()
        last_lines = int(request.query_params.get("last", 1000))
        full = request.query_params.get("full", "false").lower() == "true"

        log_file_path = os.path.join("logs", f"{build_record.job_name}_{build_record.build_number}.log")

        if not os.path.exists(log_file_path):
            return Response({"detail": "Log file not found"}, status=status.HTTP_404_NOT_FOUND)

        if full:
            with open(log_file_path, "r") as f:
                content = f.read()
        else:
            content = read_logs(log_file_path, last_lines=last_lines)  # read last N lines

        return Response({"log": content})
