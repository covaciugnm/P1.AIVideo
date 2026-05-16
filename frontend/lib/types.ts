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
  // Phase 4F-2 additions. Both are optional in the TS contract so older
  // mock fixtures or servers that haven't yet shipped the backfill still
  // type-check.
  readonly qc_passed?: boolean | null;
  readonly final_export_available?: boolean;
  // Phase 8F-1: per-job provider selection on each list row.
  readonly provider_selection?: ProviderSelection | null;
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
  readonly provider_selection: ProviderSelection | null;
  readonly rejection_reason: string | null;
  /**
   * Phase 8D operational recovery state. Optional / nullable so older
   * backends that don't return the field still typecheck.
   */
  readonly recovery_metadata?: Record<string, unknown> | null;
  readonly created_at: string;
  readonly updated_at: string;
}

/**
 * Phase 4F-2 aggregate detail response. Superset of {@link JobResponse}.
 *
 * Returned by `GET /api/v1/jobs/{id}`. The aggregate fields are computed
 * server-side from the stage_runs / artifacts / compliance_events tables.
 * The old {@link JobResponse} is still returned by `POST /api/v1/jobs`
 * (the creation-time response) and is structurally assignable to
 * {@link JobDetail} so old call sites keep working.
 */
export interface JobDetail extends JobResponse {
  readonly current_stage: string | null;
  readonly progress_percent: number;
  readonly artifact_count: number;
  readonly compliance_event_count: number;
  readonly latest_qc_result: Record<string, unknown> | null;
  readonly final_export_summary: Record<string, unknown> | null;
}

/**
 * Phase 4F-2 combined payload. Returned by
 * `GET /api/v1/jobs/{id}/summary`. Bundles the seven detail-page
 * endpoints into one response so the frontend can open the detail view
 * in a single round-trip.
 */
export interface JobFullSummary {
  readonly job: JobDetail;
  readonly progress: JobProgress;
  readonly timeline: readonly StageTimelineEntry[];
  readonly artifacts: readonly ArtifactResponse[];
  readonly compliance_events: readonly ComplianceEventResponse[];
  readonly qc_report: QCReportResponse | null;
  readonly final_export: FinalExportResponse | null;
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
  // Phase 4F-2 flat stage-name lists. Defaulted on the backend; here
  // declared optional so an older payload still type-checks.
  readonly pending_stages?: number;
  readonly completed_stage_names?: readonly string[];
  readonly failed_stage_names?: readonly string[];
  readonly pending_stage_names?: readonly string[];
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

// Phase 4F providers + TTS preview.

export type ProviderCategory =
  | "llm"
  | "tts"
  | "video_generator"
  | "audio_processor"
  | "image_processor";

export type ProviderStatus =
  | "available"
  | "configured"
  | "not_configured"
  | "not_implemented"
  | "disabled"
  | "error";

export type ProviderLocality = "local" | "external";

export interface ProviderInfo {
  readonly category: ProviderCategory;
  readonly provider_id: string;
  readonly label: string;
  readonly backend_type: string;
  readonly default_model: string | null;
  readonly is_local: boolean;
  readonly status: ProviderStatus;
  readonly notes: string;
  // Phase 6D additions — optional in the TS contract because older
  // backends may not return them.
  readonly local_or_external?: ProviderLocality;
  readonly supported_models?: readonly string[];
  readonly requires_network?: boolean;
  readonly requires_gpu?: boolean;
  readonly requires_model_files?: boolean;
  readonly healthcheck_available?: boolean;
  readonly warning?: string;
  readonly docs_url?: string;
  readonly is_custom?: boolean;
}

export interface ProvidersResponse {
  readonly llm: readonly ProviderInfo[];
  readonly tts: readonly ProviderInfo[];
  readonly video_generator: readonly ProviderInfo[];
  // Phase 6D — optional for backward-compat with older payloads.
  readonly audio_processor?: readonly ProviderInfo[];
  readonly image_processor?: readonly ProviderInfo[];
}

export interface ProviderSelection {
  readonly script_provider_id?: string | null;
  readonly script_model?: string | null;
  readonly tts_provider_id?: string | null;
  readonly tts_model?: string | null;
  readonly video_provider_id?: string | null;
  readonly video_model?: string | null;
  // Phase 6D additions.
  readonly audio_processor_id?: string | null;
  readonly image_processor_id?: string | null;
}

export interface TTSGenerateRequest {
  readonly script_text: string;
  readonly tts_provider_id: string;
  readonly tts_model?: string | null;
  readonly language?: string;
  readonly output_format?: "wav" | "mp3";
  readonly target_duration_seconds?: number | null;
}

export interface TTSGenerateError {
  readonly code:
    | "tts_provider_not_configured"
    | "tts_provider_disabled"
    | "tts_provider_not_implemented"
    // Phase 5A categorised codes.
    | "tts_runtime_missing"
    | "tts_assets_missing"
    | "tts_generation_failed";
  readonly message: string;
  readonly provider_id: string;
}

// Phase 8F-2 — success-branch type for the TTS preview endpoint
// (Phase 5A shipped this on the backend but the frontend never widened
// the union). Used by ProviderTestPanel to play back the artifact.
export interface TTSGenerateResponse {
  readonly status: "generated";
  readonly provider_id: string;
  readonly voice_id: string;
  readonly artifact_id: string;
  readonly uri: string;
  readonly mime_type: string;
  readonly checksum_sha256: string;
  readonly size_bytes: number;
  readonly duration_seconds: number;
  readonly sample_rate: number;
  readonly channels: number;
}

// Phase 5B — script generation.

export interface ScriptGenerateRequest {
  readonly brief: string;
  readonly target_duration_seconds: number;
  readonly script_text?: string | null;
  readonly tone?: string | null;
  readonly language?: string;
  readonly provider_id?: string;
  readonly model?: string | null;
}

export interface ScriptGenerateResponse {
  readonly status: "generated";
  readonly provider_id: string;
  readonly model: string;
  readonly hook: string;
  readonly body: string;
  readonly cta: string;
  readonly full_script: string;
  readonly estimated_duration_seconds: number;
  readonly language: string;
  readonly artifact_id: string | null;
  readonly message: string;
}

export interface ScriptGenerateError {
  readonly code:
    | "script_provider_not_configured"
    | "script_provider_disabled"
    | "script_provider_unreachable"
    | "script_provider_not_implemented"
    | "script_generation_failed"
    // Phase 8G-2 — distinct from unreachable. Daemon answered, but the
    // selected model isn't pulled.
    | "script_model_missing";
  readonly message: string;
  readonly provider_id: string;
}

// Phase 5C — audio fit-check.

export type FitStatus = "ok" | "too_short" | "too_long" | "missing_audio";
export type FitRecommendation =
  | "accept"
  | "regenerate_script_shorter"
  | "regenerate_script_longer"
  | "adjust_target_duration"
  | "upload_better_audio";

export interface AudioFitCheckRequest {
  readonly job_id?: string | null;
  readonly script_text?: string | null;
  readonly audio_artifact_id?: string | null;
  readonly target_duration_seconds?: number | null;
}

export interface AudioFitCheckResponse {
  readonly target_duration_seconds: number;
  readonly audio_duration_seconds: number | null;
  readonly delta_seconds: number | null;
  readonly fit_status: FitStatus;
  readonly recommendation: FitRecommendation;
  readonly audio_artifact_id: string | null;
  readonly job_id: string | null;
  readonly metadata: Record<string, unknown>;
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
  readonly provider_selection?: ProviderSelection | null;
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
  readonly provider_selection?: ProviderSelection | null;
}
