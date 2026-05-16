// Phase 11A — shared i18n types.
//
// One ``Dictionary`` shape, two implementations (en + ro) under
// ``./dictionaries/{en,ro}.ts``. Adding a new visible string in a
// component means adding a key here AND filling it in BOTH dictionaries.
// The Phase 11A test suite asserts:
// - both dictionaries declare the same key set,
// - no empty values, and
// - every component listed in ``test_phase11a_ui_i18n_static.py``
//   imports useT and calls t() at least once.

export type LanguageCode = "ro" | "en";

export const SUPPORTED_LANGUAGE_CODES: readonly LanguageCode[] = ["ro", "en"];

export const DEFAULT_LANGUAGE: LanguageCode = "ro";

export interface LanguageMeta {
  readonly code: LanguageCode;
  readonly labelNative: string;
  readonly labelEnglish: string;
  readonly rtl: boolean;
}

export const LANGUAGE_META: Readonly<Record<LanguageCode, LanguageMeta>> = {
  ro: { code: "ro", labelNative: "Română", labelEnglish: "Romanian", rtl: false },
  en: { code: "en", labelNative: "English", labelEnglish: "English", rtl: false },
};

/** Shape every dictionary must fill in. Updating a key in one language
 * but not the other is caught by the parity test. */
export interface Dictionary {
  readonly nav: Readonly<Record<
    "dashboard" | "jobs" | "newJob" | "uploads" | "settings" | "help",
    string
  >>;
  readonly common: Readonly<Record<
    | "save"
    | "cancel"
    | "delete"
    | "edit"
    | "view"
    | "retry"
    | "refresh"
    | "reset"
    | "copy"
    | "copied"
    | "upload"
    | "download"
    | "test"
    | "status"
    | "provider"
    | "language"
    | "subtitles"
    | "error"
    | "loading"
    | "noData"
    | "close"
    | "open"
    | "yes"
    | "no"
    | "back"
    | "forward"
    | "search"
    | "available"
    | "notConfigured"
    | "notImplemented"
    | "runtimeMissing"
    | "assetsMissing"
    | "preview"
    | "details"
    | "showMore"
    | "showLess"
    | "submit"
    | "submitting"
    | "characters"
    | "between"
    | "noFace"
    | "type"
    | "id"
    | "size"
    | "duration"
    | "dimensions"
    | "checksum"
    | "created"
    | "actions"
    | "name"
    | "label"
    | "value"
    | "manifest"
    | "manifestOnly"
    | "realMp4"
    | "metadataOnly"
    | "realMedia"
    | "real"
    | "stub"
    | "pending"
    | "passed"
    | "failed"
    | "skipped"
    | "ready"
    | "running"
    | "succeeded"
    | "rejected"
    | "warn"
    | "info"
    | "ok"
    | "off"
    | "on",
    string
  >>;
  readonly dashboard: Readonly<Record<
    "title" | "recentJobs" | "qc" | "finalExport" | "updated" | "progress" | "noJobsYet" | "newJob",
    string
  >>;
  readonly jobs: Readonly<Record<
    | "title"
    | "brief"
    | "status"
    | "voice"
    | "face"
    | "progress"
    | "currentStage"
    | "duration"
    | "artifacts"
    | "actions"
    | "filterByStatus"
    | "filterAll"
    | "noJobs"
    | "noJobsForFilter"
    | "newJob"
    | "created"
    | "language"
    | "view"
    | "delete"
    | "deleteConfirm"
    | "loadingJobs"
    | "failedToLoad"
    | "deleteFailed"
    | "deleting"
    | "confirmDelete"
    | "abortDelete"
    | "jobsCount"
    | "voiceOverFace"
    | "checkBackendUrl",
    string
  >>;
  readonly statusLabels: Readonly<Record<
    | "pending_compliance"
    | "accepted"
    | "published"
    | "rejected"
    | "failed"
    | "succeeded"
    | "running"
    | "skipped"
    | "pending"
    | "available"
    | "not_ready",
    string
  >>;
  readonly stageLabels: Readonly<Record<
    | "compliance"
    | "identity_guard"
    | "scriptwriter"
    | "voice"
    | "face"
    | "pre_lipsync_auth"
    | "lipsync"
    | "editor"
    | "qc"
    | "publisher"
    | "export_disclosure_validation"
    | "policy_gate",
    string
  >>;
  readonly createJob: Readonly<Record<
    | "title"
    | "intro"
    | "sectionBrief"
    | "briefLabel"
    | "briefPlaceholder"
    | "targetDuration"
    | "durationBetween"
    | "sectionVoice"
    | "voiceMode"
    | "voiceTts"
    | "voiceProvided"
    | "scriptText"
    | "scriptPlaceholder"
    | "scriptCounter"
    | "sectionProviders"
    | "scriptProvider"
    | "ttsProvider"
    | "videoProvider"
    | "audioProcessor"
    | "imageProcessor"
    | "providerInherit"
    | "providerInheritWithName"
    | "providersUnavailable"
    | "providerSelected"
    | "sectionFace"
    | "useProvidedImage"
    | "providedImageTitle"
    | "imageConsent"
    | "imageSynthetic"
    | "audioConsent"
    | "audioOwned"
    | "audioFitCheck"
    | "audioFitChecking"
    | "providedAudioTitle"
    | "sectionLanguage"
    | "languageIntro"
    | "videoLanguage"
    | "enableSubtitles"
    | "subtitleLanguages"
    | "subtitleFormat"
    | "burnSubtitles"
    | "burnNotImplemented"
    | "sectionCompliance"
    | "complianceBanner"
    | "syntheticConfirm"
    | "consentConfirm"
    | "generateScript"
    | "generateScriptBusy"
    | "generateAudio"
    | "generateAudioBusy"
    | "listen"
    | "uploadAudio"
    | "uploadImage"
    | "submit"
    | "submitting"
    | "providerNotConfigured"
    | "providerRequiresGpu"
    | "providerRequiresModelFiles"
    | "watermarkRequired"
    | "c2paRequired"
    | "scriptArtifactCreated"
    | "audioArtifactCreated"
    | "scriptGeneratedPreview"
    | "scriptFailed"
    | "audioFailed"
    | "missingScriptText"
    | "missingAudioRef"
    | "missingImageRef",
    string
  >>;
  readonly uploads: Readonly<Record<
    | "title"
    | "intro"
    | "textUpload"
    | "audioUpload"
    | "imageUpload"
    | "recentUploads"
    | "noRecent"
    | "acceptedFormats"
    | "maxFileSize"
    | "uploadSuccessful"
    | "uploadFailed"
    | "selectFile"
    | "clear"
    | "selected"
    | "dropFiles"
    | "currentArtifact"
    | "uploadHint"
    | "textHelp"
    | "audioHelp"
    | "imageHelp"
    | "textTitleField"
    | "languageField"
    | "toneField"
    | "scriptField",
    string
  >>;
  readonly settings: Readonly<Record<
    | "title"
    | "intro"
    | "backendUrl"
    | "backendUrlHint"
    | "backendUrlAutoHint"
    | "backendUrlCustomHint"
    | "testBackend"
    | "testing"
    | "testSuccess"
    | "testFailed"
    | "dockerPorts"
    | "dockerPortsHint"
    | "pollingInterval"
    | "autoPolling"
    | "logsSection"
    | "providerDefaults"
    | "customProviders"
    | "interfaceLanguage"
    | "defaultVideoLanguage"
    | "resetDefaults"
    | "save"
    | "copyComposeCmd"
    | "composeCmdLabel"
    | "showFrontendLogs"
    | "showBackendLogs"
    | "showApiLogs"
    | "showSystemLogs"
    | "backendPort"
    | "frontendPort"
    | "postgresPort"
    | "redisPort"
    | "testPort"
    | "portReachable"
    | "portUnreachable"
    | "providerDefaultsHint"
    | "customProvidersHint",
    string
  >>;
  readonly jobDetail: Readonly<Record<
    | "overview"
    | "timeline"
    | "artifacts"
    | "complianceEvents"
    | "qcReport"
    | "finalExport"
    | "recoveryControls"
    | "cancelJob"
    | "cancelling"
    | "retryJob"
    | "retrying"
    | "metadataOnly"
    | "realMedia"
    | "preview"
    | "downloadArtifact"
    | "language"
    | "subtitlesOn"
    | "subtitlesOff"
    | "subtitleLanguages"
    | "subtitleFormat"
    | "burnInStatus"
    | "noVideoYet"
    | "noQcYet"
    | "noExportYet"
    | "rejected"
    | "rejectionReason"
    | "backToJobs"
    | "editJob"
    | "deleteJob"
    | "briefField"
    | "targetDuration"
    | "voiceMode"
    | "faceMode"
    | "ttsBackend"
    | "watermarkRequired"
    | "c2paRequired"
    | "videoLanguage"
    | "subtitles"
    | "createdAt"
    | "updatedAt"
    | "burnInSidecar"
    | "burnInRequested"
    | "noArtifacts"
    | "terminalNote"
    | "terminalCancelDisabled"
    | "terminalRetryDisabled"
    | "cancelReason"
    | "cancelReasonPlaceholder"
    | "retryReason"
    | "retryReasonPlaceholder"
    | "retryFromStage"
    | "videoPreview"
    | "downloadMp4"
    | "fallbackVideo"
    | "watermarkBadge"
    | "c2paBadge"
    | "finalExportBadge",
    string
  >>;
  readonly providers: Readonly<Record<
    | "testProvider"
    | "runtimeMissing"
    | "assetsMissing"
    | "notConfigured"
    | "notImplemented"
    | "requiresGpu"
    | "requiresNetwork"
    | "requiresModelFiles"
    | "providerStatus"
    | "testResult"
    | "addCustom"
    | "customName"
    | "customCategory"
    | "customBaseUrl"
    | "category"
    | "backendType"
    | "defaultModel"
    | "label"
    | "isLocal"
    | "notes"
    | "docsLink"
    | "warning"
    | "categoryLlm"
    | "categoryTts"
    | "categoryVideo"
    | "categoryAudioProcessor"
    | "categoryImageProcessor"
    | "selectProvider"
    | "noProviders"
    | "test1Title"
    | "test1Intro"
    | "diagnosticsRunning"
    | "diagnosticsOk"
    | "diagnosticsFailed",
    string
  >>;
  readonly logs: Readonly<Record<
    | "title"
    | "exportJson"
    | "exportTxt"
    | "clearLogs"
    | "sessionLocal"
    | "logLevel"
    | "source"
    | "noEntries"
    | "filterByLevel"
    | "allLevels"
    | "filterCount"
    | "expand"
    | "collapse"
    | "info"
    | "warning"
    | "errorLevel"
    | "successLevel"
    | "sourceFrontend"
    | "sourceApi"
    | "sourceBackend"
    | "sourceSystem",
    string
  >>;
  readonly help: Readonly<Record<
    | "open"
    | "close"
    | "search"
    | "related"
    | "searchPlaceholder"
    | "noResults",
    string
  >>;
  readonly errors: Readonly<Record<
    | "script_provider_disabled"
    | "script_model_missing"
    | "script_provider_unreachable"
    | "script_generation_failed"
    | "tts_runtime_missing"
    | "tts_assets_missing"
    | "tts_generation_failed"
    | "tts_provider_not_configured"
    | "tts_provider_not_implemented"
    | "video_assets_missing"
    | "video_gpu_missing"
    | "video_runtime_missing"
    | "video_provider_not_configured"
    | "video_provider_not_implemented"
    | "provider_not_implemented"
    | "provider_not_configured"
    | "artifact_not_found"
    | "upload_failed"
    | "validation_error"
    | "unknown",
    string
  >>;
  readonly sidebar: Readonly<Record<
    "logs" | "settings" | "test1" | "activity" | "collapse" | "expand",
    string
  >>;
  readonly artifactTable: Readonly<Record<
    | "header_type"
    | "header_id"
    | "header_mime"
    | "header_size"
    | "header_dim"
    | "header_sha"
    | "header_real"
    | "header_created"
    | "real_yes"
    | "real_no"
    | "real_metadata"
    | "real_manifest"
    | "empty",
    string
  >>;
  readonly qc: Readonly<Record<
    | "title"
    | "targetDuration"
    | "segments"
    | "script"
    | "editPlan"
    | "reelDraftUri"
    | "checksHeading"
    | "metadataOnlyNote"
    | "realMediaNote",
    string
  >>;
  readonly finalExportLabels: Readonly<Record<
    | "title"
    | "exportUri"
    | "exportType"
    | "targetDuration"
    | "watermarkRequired"
    | "c2paRequired"
    | "reelDraft"
    | "qcReport"
    | "note"
    | "noEncodedVideoNote",
    string
  >>;
  readonly recovery: Readonly<Record<
    | "title"
    | "terminalNote"
    | "terminalCancelDisabled"
    | "terminalRetryDisabled"
    | "retryFromStage"
    | "retryAvailable"
    | "retryNotAvailable"
    | "cancelReason"
    | "cancelReasonPlaceholder"
    | "retryReason"
    | "retryReasonPlaceholder"
    | "cancelHistory"
    | "retryHistory"
    | "lastError",
    string
  >>;
  readonly compliance: Readonly<Record<
    | "title"
    | "events"
    | "stage"
    | "decision"
    | "reason"
    | "createdAt"
    | "noEvents"
    | "extra",
    string
  >>;
  readonly customProviders: Readonly<Record<
    | "title"
    | "intro"
    | "add"
    | "edit"
    | "remove"
    | "providerId"
    | "category"
    | "label"
    | "baseUrl"
    | "isLocal"
    | "requiresGpu"
    | "requiresModelFiles"
    | "notes"
    | "save"
    | "cancel"
    | "noCustom"
    | "validationError",
    string
  >>;
  readonly providersSection: Readonly<Record<
    | "title"
    | "intro"
    | "scriptDefault"
    | "ttsDefault"
    | "videoDefault"
    | "ttsTestTitle"
    | "ttsTestRunning"
    | "ttsTestSuccess"
    | "ttsTestFailure"
    | "providersLoading"
    | "providersFailed",
    string
  >>;
  readonly footer: Readonly<Record<
    "complianceLine" | "helpLink",
    string
  >>;
  readonly badges: Readonly<Record<
    | "gpuRequired"
    | "requiresNetwork"
    | "requiresModelFiles"
    | "customMetadataOnly"
    | "qcGate"
    | "aiDisclosureStatus"
    | "manifestOnly"
    | "realMp4"
    | "interfaceLanguage"
    | "openSettingsToChangeUrl"
    | "completedStages"
    | "currentStage"
    | "test1Description"
    | "uploadedImagePreview"
    | "uploadedAudioPreview"
    | "fillBriefFirst",
    string
  >>;
  readonly editJob: Readonly<Record<
    | "title"
    | "failedToLoad"
    | "updateRejected"
    | "editable"
    | "noChanges"
    | "saving"
    | "saveChanges"
    | "savingDone"
    | "lockedAfterCompliance"
    | "lockedTerminal"
    | "backToJob"
    | "readOnly"
    | "terminalNote"
    | "complianceLockedNote"
    | "briefLabel"
    | "targetDurationLabel"
    | "scriptTextLabel"
    | "loadingJob"
    | "publishedLockedNote"
    | "cannotEditCurrent"
    | "cannotEditThisJob"
    | "someFieldsLocked"
    | "providerChangeableBeforeRetry"
    | "providerEditIntro"
    | "saveBeforeRetry"
    | "retryAfterEdit"
    | "changesSaved",
    string
  >>;
  readonly uploadsPage: Readonly<Record<
    | "sectionText"
    | "sectionAudio"
    | "sectionImage"
    | "recentTab"
    | "noUploadsYet"
    | "localToTab"
    | "copyId"
    | "titleOptional"
    | "registerText"
    | "registering"
    | "scriptCannotBeEmpty"
    | "failedToLoadOptions"
    | "uploadAudioTitle"
    | "uploadImageTitle",
    string
  >>;
  readonly stageTimeline: Readonly<Record<
    | "completedStages"
    | "currentStage"
    | "failedStages"
    | "pendingStages"
    | "noStages",
    string
  >>;
  readonly recoveryHistory: Readonly<Record<
    | "cancelledAt"
    | "cancellationReason"
    | "retryRequestedAt"
    | "retryCount"
    | "lastError"
    | "history",
    string
  >>;
  readonly providerSelection: Readonly<Record<
    | "warningPrefix"
    | "warningSuffixCleanError"
    | "warningRequires"
    | "subtitleFormatSrt"
    | "subtitleFormatVtt",
    string
  >>;
  // Phase 11A-FIX additions — sections used by the formatters helper
  // and by components that previously relied on humanize() or
  // hardcoded English.
  readonly statuses: Readonly<Record<
    | "pending_compliance"
    | "accepted"
    | "published"
    | "rejected"
    | "failed"
    | "running"
    | "succeeded"
    | "skipped"
    | "pending"
    | "cancelled"
    | "unknown",
    string
  >>;
  readonly stages: Readonly<Record<
    | "policy_gate"
    | "scriptwriter"
    | "voice"
    | "face"
    | "identity_guard"
    | "pre_lipsync_auth"
    | "lipsync"
    | "editor"
    | "qc"
    | "publisher"
    | "export_disclosure_validation"
    | "compliance"
    | "completed"
    | "failed"
    | "pending"
    | "running",
    string
  >>;
  readonly artifactTypes: Readonly<Record<
    | "script"
    | "audio"
    | "image"
    | "video"
    | "final_export"
    | "qc_report"
    | "edit_plan"
    | "subtitle"
    | "manifest"
    | "metadata"
    | "unknown",
    string
  >>;
  readonly voiceModes: Readonly<Record<
    | "tts"
    | "provided_audio",
    string
  >>;
  readonly faceModes: Readonly<Record<
    | "provided_image"
    | "none",
    string
  >>;
  readonly providerStatuses: Readonly<Record<
    | "available"
    | "configured"
    | "not_configured"
    | "not_implemented"
    | "disabled"
    | "error"
    | "unknown",
    string
  >>;
  readonly runtime: Readonly<Record<
    | "audioFitOk"
    | "audioFitTooShort"
    | "audioFitTooLong"
    | "audioFitMissingAudio"
    | "audioFitLabel"
    | "audioFitRecAccept"
    | "audioFitRecRegenScriptShorter"
    | "audioFitRecRegenScriptLonger"
    | "audioFitRecAdjustDuration"
    | "audioFitRecUploadBetterAudio"
    | "qcDecisionPass"
    | "qcDecisionFail"
    | "qcDecisionWarn",
    string
  >>;
  readonly validation: Readonly<Record<
    | "required"
    | "invalidType"
    | "valueTooShort"
    | "valueTooLong"
    | "invalidEnum"
    | "syntheticPersonRequired"
    | "consentRequired"
    | "scriptTextRequiredForTts"
    | "targetDurationRange"
    | "providerSelectionInvalidKey"
    | "unknownJob"
    | "backendUnavailable"
    | "httpError"
    | "extraForbiddenField"
    | "watermarkRequiredTrue"
    | "c2paRequiredTrue"
    | "languageNotSupported",
    string
  >>;
  readonly time: Readonly<Record<
    | "justNow"
    | "secondsAgo"
    | "minutesAgo"
    | "hoursAgo"
    | "daysAgo",
    string
  >>;
  readonly progressBar: Readonly<Record<
    | "ariaLabel"
    | "stagesUnit"
    | "failedSuffix",
    string
  >>;
  readonly logsPanel: Readonly<Record<
    | "showDetails"
    | "hideDetails"
    | "exportedFormat",
    string
  >>;
  readonly uploadCard: Readonly<Record<
    | "fileTooLarge"
    | "unsupportedExtension"
    | "selectedFileSize"
    | "currentArtifactShort"
    | "maxFileSizeLabel",
    string
  >>;
  readonly complianceList: Readonly<Record<
    | "empty",
    string
  >>;
}
