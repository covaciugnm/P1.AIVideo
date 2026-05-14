// Mirrors the Pydantic schemas in backend/app/schemas/*. Every type here
// is metadata-only — no binary payloads cross the API boundary.

export type JobStatus =
  | "pending_compliance"
  | "accepted"
  | "published"
  | "rejected"
  | "failed";

export type StageStatus =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "rejected"
  | "skipped";

export type ComplianceDecision = "accept" | "reject";

export type VoiceMode = "tts" | "provided_audio";
export type FaceMode = "provided_image";

export type QCDecision = "pass" | "fail" | "warn";

export type FinalExportStatus = "published" | "blocked" | "skipped";
export type DisclosureStatus = "pending" | "embedded" | "missing";

export interface JobSummary {
  readonly id: string;
  readonly status: JobStatus;
  readonly brief: string;
  readonly target_duration_seconds: number;
  readonly voice_mode: string;
  readonly face_mode: string | null;
  readonly created_at: string;
  readonly updated_at: string;
  readonly current_stage: string | null;
  readonly progress_percent: number;
  readonly artifact_count: number;
}

export interface JobResponse {
  readonly id: string;
  readonly status: JobStatus;
  readonly brief: string;
  readonly target_duration_seconds: number;
  readonly watermark_required: boolean;
  readonly c2pa_required: boolean;
  readonly voice_mode: string;
  readonly script_text: string | null;
  readonly tts_backend: string;
  readonly audio_ref: Record<string, unknown> | null;
  readonly face_mode: string | null;
  readonly image_ref: Record<string, unknown> | null;
  readonly rejection_reason: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface StageProgress {
  readonly stage_name: string;
  readonly status: StageStatus | "pending";
  readonly started_at: string | null;
  readonly completed_at: string | null;
}

export interface JobProgress {
  readonly job_id: string;
  readonly status: JobStatus;
  readonly total_stages: number;
  readonly completed_stages: number;
  readonly failed_stages: number;
  readonly current_stage: string | null;
  readonly progress_percent: number;
  readonly stages: readonly StageProgress[];
}

export interface StageTimelineEntry {
  readonly stage_name: string;
  readonly status: string;
  readonly started_at: string;
  readonly completed_at: string | null;
  readonly duration_ms: number | null;
  readonly error_message: string | null;
  readonly artifact_refs: readonly string[];
  readonly metadata_summary: Record<string, unknown>;
}

export interface ArtifactResponse {
  readonly artifact_id: string;
  readonly artifact_type: string;
  readonly uri: string;
  readonly mime_type: string | null;
  readonly checksum_sha256: string | null;
  readonly size_bytes: number | null;
  readonly duration_seconds: number | null;
  readonly width: number | null;
  readonly height: number | null;
  readonly sample_rate: number | null;
  readonly channels: number | null;
  readonly local_path: string | null;
  readonly created_at: string;
  readonly stage_run_id: string | null;
  readonly metadata_summary: Record<string, unknown>;
}

export interface ComplianceEventResponse {
  readonly event_type: string;
  readonly decision: ComplianceDecision;
  readonly reasons: readonly string[];
  readonly created_at: string;
  readonly metadata_summary: Record<string, unknown>;
}

export interface QCCheck {
  readonly name: string;
  readonly decision: QCDecision;
  readonly detail: string;
  readonly metadata?: Record<string, unknown>;
}

export interface QCReport {
  readonly passed: boolean;
  readonly checks: readonly QCCheck[];
  readonly script_artifact_uri: string;
  readonly script_artifact_checksum: string | null;
  readonly edit_plan_artifact_uri: string;
  readonly edit_plan_artifact_checksum: string | null;
  readonly reel_draft_artifact_uri: string;
  readonly target_duration_seconds: number;
  readonly segment_count: number;
  readonly expected_segments: readonly string[];
  readonly metadata?: Record<string, unknown>;
}

export interface QCReportResponse {
  readonly job_id: string;
  readonly artifact_id: string;
  readonly artifact_uri: string;
  readonly checksum_sha256: string | null;
  readonly qc_report: QCReport;
  readonly created_at: string;
}

export interface FinalExport {
  readonly passed_qc: boolean;
  readonly status: FinalExportStatus;
  readonly job_id: string;
  readonly source_reel_draft_uri: string;
  readonly source_reel_draft_checksum: string | null;
  readonly qc_report_uri: string;
  readonly qc_report_checksum: string | null;
  readonly export_uri: string;
  readonly export_type: string;
  readonly mime_type: string;
  readonly target_duration_seconds: number;
  readonly watermark_required: boolean;
  readonly c2pa_required: boolean;
  readonly disclosure_status: DisclosureStatus;
  readonly metadata?: Record<string, unknown>;
}

export interface FinalExportResponse {
  readonly job_id: string;
  readonly artifact_id: string;
  readonly artifact_uri: string;
  readonly checksum_sha256: string | null;
  readonly final_export: FinalExport;
  readonly created_at: string;
}

// Phase 4B metadata endpoints.

export interface StageInfo {
  readonly name: string;
  readonly order: number;
  readonly label: string;
}

export interface ArtifactTypeInfo {
  readonly value: string;
  readonly label: string;
}

export interface VoiceModeInfo {
  readonly value: VoiceMode;
  readonly label: string;
  readonly requires_script_text: boolean;
  readonly requires_audio_artifact: boolean;
}

export interface FaceModeInfo {
  readonly value: FaceMode;
  readonly label: string;
  readonly requires_image_artifact: boolean;
}

export interface DurationBounds {
  readonly min_seconds: number;
  readonly max_seconds: number;
  readonly default_seconds: number;
}

export interface UploadLimits {
  readonly audio_max_bytes: number;
  readonly image_max_bytes: number;
  readonly script_text_max_chars: number;
  readonly accepted_audio_mime_types: readonly string[];
  readonly accepted_image_mime_types: readonly string[];
  readonly accepted_audio_extensions: readonly string[];
  readonly accepted_image_extensions: readonly string[];
}

export interface UIOptions {
  readonly voice_modes: readonly VoiceModeInfo[];
  readonly face_modes: readonly FaceModeInfo[];
  readonly tts_backends: readonly string[];
  readonly duration_bounds: DurationBounds;
  readonly upload_limits: UploadLimits;
  readonly job_statuses: readonly string[];
  readonly stage_statuses: readonly string[];
  readonly provider_health_statuses: readonly string[];
  readonly artifact_types: readonly ArtifactTypeInfo[];
}

export interface SystemStatus {
  readonly app_name: string;
  readonly app_version: string;
  readonly phase: string;
  readonly scope: string;
  readonly server_time: string;
  readonly database_reachable: boolean;
  readonly database_error: string | null;
}

// Upload responses.

export interface UploadTextResponse {
  readonly artifact_id: string;
  readonly artifact_type: string;
  readonly uri: string;
  readonly mime_type: string | null;
  readonly checksum_sha256: string | null;
  readonly size_bytes: number | null;
  readonly script_ref: Record<string, unknown>;
  readonly metadata_summary: Record<string, unknown>;
}

export interface UploadAudioResponse {
  readonly artifact_id: string;
  readonly artifact_type: string;
  readonly uri: string;
  readonly local_path: string;
  readonly mime_type: string;
  readonly checksum_sha256: string;
  readonly size_bytes: number;
  readonly duration_seconds: number;
  readonly sample_rate: number;
  readonly channels: number;
  readonly audio_ref: Record<string, unknown>;
  readonly metadata_summary: Record<string, unknown>;
}

export interface UploadImageResponse {
  readonly artifact_id: string;
  readonly artifact_type: string;
  readonly uri: string;
  readonly local_path: string;
  readonly mime_type: string;
  readonly checksum_sha256: string;
  readonly size_bytes: number;
  readonly width: number;
  readonly height: number;
  readonly image_ref: Record<string, unknown>;
  readonly metadata_summary: Record<string, unknown>;
}

export interface CreateJobBody {
  readonly brief: string;
  readonly synthetic_person_confirmed: boolean;
  readonly consent_confirmed: boolean;
  readonly target_duration_seconds: number;
  readonly watermark_required: boolean;
  readonly c2pa_required: boolean;
  readonly voice_mode: VoiceMode;
  readonly script_text: string | null;
  readonly tts_backend?: string;
  readonly audio_ref?: Record<string, unknown> | null;
  readonly face_mode?: FaceMode | null;
  readonly image_ref?: Record<string, unknown> | null;
}

export interface CreateJobFromInputsBody {
  readonly brief: string;
  readonly target_duration_seconds: number;
  readonly synthetic_person_confirmed: boolean;
  readonly consent_confirmed: boolean;
  readonly watermark_required: boolean;
  readonly c2pa_required: boolean;
  readonly voice_mode: VoiceMode;
  readonly face_mode: FaceMode | null;
  readonly script_artifact_id?: string | null;
  readonly script_text?: string | null;
  readonly audio_artifact_id?: string | null;
  readonly audio_consent_confirmed?: boolean;
  readonly audio_synthetic_or_owned?: boolean;
  readonly image_artifact_id?: string | null;
  readonly image_consent_confirmed?: boolean;
  readonly image_synthetic_person_confirmed?: boolean;
}
