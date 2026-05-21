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
    "dashboard" | "jobs" | "newJob" | "uploads" | "characters" | "settings" | "help" | "technical",
    string
  >>;
  readonly technical: Readonly<Record<
    | "title"
    | "subtitle"
    | "searchPlaceholder"
    | "noResults"
    | "loading"
    | "failedToLoad"
    | "openButton"
    | "downloadMarkdown"
    | "sourcePath"
    | "generatedAt"
    | "tocTitle"
    | "matchCount",
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
    | "on"
    | "romanian"
    | "english",
    string
  >>;
  readonly dashboard: Readonly<Record<
    "title" | "recentJobs" | "qc" | "finalExport" | "updated" | "progress" | "noJobsYet" | "newJob",
    string
  >>;
  readonly jobs: Readonly<Record<
    | "title" | "brief" | "status" | "voice" | "face" | "progress" | "currentStage" | "duration" | "artifacts" | "actions" | "filterByStatus" | "filterAll" | "noJobs" | "noJobsForFilter" | "newJob" | "created" | "language" | "view" | "delete" | "deleteConfirm" | "loadingJobs" | "failedToLoad" | "deleteFailed" | "deleting" | "confirmDelete" | "abortDelete" | "jobsCount" | "voiceOverFace" | "checkBackendUrl",
    string
  >>;
  readonly statusLabels: Readonly<Record<
    | "pending_compliance" | "accepted" | "published" | "rejected" | "failed" | "succeeded" | "running" | "skipped" | "pending" | "available" | "not_ready",
    string
  >>;
  readonly stageLabels: Readonly<Record<
    | "compliance" | "identity_guard" | "scriptwriter" | "voice" | "face" | "pre_lipsync_auth" | "lipsync" | "editor" | "qc" | "publisher" | "export_disclosure_validation" | "policy_gate",
    string
  >>;
  readonly createJob: Readonly<Record<
    | "title" | "intro" | "sectionJobType" | "jobTypeIntro" | "jobTypeTalkingHead" | "jobTypeTalkingHeadDesc" | "jobTypeScenesOnly" | "jobTypeScenesOnlyDesc" | "jobTypeNewsPresenter" | "jobTypeNewsPresenterDesc" | "jobTypeComingSoon" | "jobTypeScenesOnlyPending" | "jobTypeNewsPresenterPending" | "orientationLabel" | "orientationLandscape" | "orientationPortrait" | "orientationSquare" | "orientationHelp" | "sectionScenePlan" | "scenePlanGenerate" | "scenePlanRegenerate" | "scenePlanBusy" | "scenePlanHelp" | "scenePlanEmpty" | "scenePlanEmptyPlaceholder" | "scenePlanDone" | "scenePlanTotal" | "scenePlanAddBroll" | "scenePlanAddBrollHelp" | "scenePlanAddPresenter" | "scenePlanAddPresenterHelp" | "scenePlanKindPresenter" | "scenePlanKindBroll" | "scenePlanKindHelp" | "scenePlanDuration" | "scenePlanMoveUp" | "scenePlanMoveDown" | "scenePlanDelete" | "scenePlanSpokenText" | "scenePlanSpokenPlaceholder" | "scenePlanVisualDesc" | "scenePlanVisualPlaceholder" | "scenePlanPresenterNote" | "sectionBrief" | "briefLabel" | "briefHelp" | "briefMinChars" | "scriptMinChars" | "briefPlaceholder" | "targetDuration" | "durationBetween" | "sectionVoice" | "voiceMode" | "voiceTts" | "voiceProvided" | "scriptText" | "scriptTextHelp" | "scriptPlaceholder" | "scriptCounter" | "generateScriptHelp" | "generateAudioHelp" | "sectionProviders" | "scriptProvider" | "scriptProviderHelp" | "ttsProvider" | "ttsProviderHelp" | "videoProvider" | "audioProcessor" | "imageProcessor" | "providerInherit" | "providerInheritWithName" | "providersUnavailable" | "providerSelected" | "providerInformational" | "sectionFace" | "useProvidedImage" | "providedImageTitle" | "imageConsent" | "imageSynthetic" | "audioConsent" | "audioOwned" | "audioFitCheck" | "audioFitChecking" | "providedAudioTitle" | "sectionLanguage" | "languageIntro" | "videoLanguage" | "enableSubtitles" | "subtitleLanguages" | "subtitleFormat" | "burnSubtitles" | "burnNotImplemented" | "burnSubtitlesNote" | "subtitleTextLanguage" | "subtitleTextLanguageHelp" | "subtitleTextLanguageSameAsSpoken" | "sectionCompliance" | "complianceBanner" | "syntheticConfirm" | "consentConfirm" | "generateScript" | "generateScriptBusy" | "generateAudio" | "generateAudioBusy" | "generateScenario" | "scenarioLabel" | "scenarioHelp" | "scenarioReadonlyNote" | "scenarioEmpty" | "imageDescLabel" | "imageDescHelp" | "imageDescEditableNote" | "imageDescEmpty" | "imageGenButton" | "imageGenBusy" | "imageGenHelp" | "imageGenNoCharacter" | "imageGenNeedDesc" | "imageGenDone" | "imageGenPreviewAlt" | "imageGenPreviewNote" | "imageGenClear" | "imageGenClearHelp" | "faceUsingGeneratedTitle" | "faceUsingGeneratedDesc" | "faceSwitchToManual" | "textScriptProvider" | "textScriptProviderHelp" | "generateTextScript" | "generateTextScriptHelp" | "generateTextScriptDisabledFilled" | "generateTextScriptDisabledNoSource" | "generateTextScriptOverwriteHint" | "generateTextScriptOverwriteConfirm" | "ttsGenderFiltered" | "ttsFilteredBy" | "sectionLanguagePicker" | "languagePickerIntro" | "videoLanguageHelp" | "characterLanguagesNote" | "languageNoneAvailable" | "languageSectionSubtitleIntro" | "samplePlayUnsupported" | "listen" | "uploadAudio" | "uploadImage" | "submit" | "submitting" | "providerNotConfigured" | "providerRequiresGpu" | "providerRequiresModelFiles" | "watermarkRequired" | "c2paRequired" | "scriptArtifactCreated" | "audioArtifactCreated" | "scriptGeneratedPreview" | "scriptFailed" | "audioFailed" | "missingScriptText" | "missingAudioRef" | "missingImageRef" | "scriptGeneratedStatus" | "ttsGeneratedStatus" | "ttsPreviewLabel",
    string
  >>;
  readonly uploads: Readonly<Record<
    | "title" | "intro" | "textUpload" | "audioUpload" | "imageUpload" | "recentUploads" | "noRecent" | "acceptedFormats" | "maxFileSize" | "uploadSuccessful" | "uploadFailed" | "selectFile" | "clear" | "selected" | "dropFiles" | "currentArtifact" | "uploadHint" | "textHelp" | "audioHelp" | "imageHelp" | "textTitleField" | "languageField" | "toneField" | "scriptField",
    string
  >>;
  readonly settings: Readonly<Record<
    | "title" | "intro" | "backendUrl" | "backendUrlHint" | "backendUrlAutoHint" | "backendUrlCustomHint" | "testBackend" | "testing" | "testSuccess" | "testFailed" | "dockerPorts" | "dockerPortsHint" | "pollingInterval" | "autoPolling" | "logsSection" | "providerDefaults" | "customProviders" | "interfaceLanguage" | "defaultVideoLanguage" | "resetDefaults" | "save" | "copyComposeCmd" | "composeCmdLabel" | "showFrontendLogs" | "showBackendLogs" | "showApiLogs" | "showSystemLogs" | "backendPort" | "frontendPort" | "postgresPort" | "redisPort" | "testPort" | "portReachable" | "portUnreachable" | "providerDefaultsHint" | "customProvidersHint" | "postgresIndirectNote" | "redisRawTcpNote" | "browserDiagnosticsNote",
    string
  >>;
  readonly jobDetail: Readonly<Record<
    | "overview" | "timeline" | "artifacts" | "complianceEvents" | "qcReport" | "finalExport" | "recoveryControls" | "cancelJob" | "cancelling" | "retryJob" | "retrying" | "metadataOnly" | "realMedia" | "preview" | "downloadArtifact" | "language" | "subtitlesOn" | "subtitlesOff" | "subtitleLanguages" | "subtitleFormat" | "burnInStatus" | "noVideoYet" | "noQcYet" | "noExportYet" | "rejected" | "rejectionReason" | "backToJobs" | "editJob" | "deleteJob" | "briefField" | "targetDuration" | "voiceMode" | "faceMode" | "ttsBackend" | "watermarkRequired" | "c2paRequired" | "videoLanguage" | "subtitles" | "createdAt" | "updatedAt" | "burnInSidecar" | "burnInRequested" | "noArtifacts" | "terminalNote" | "terminalCancelDisabled" | "terminalRetryDisabled" | "cancelReason" | "cancelReasonPlaceholder" | "retryReason" | "retryReasonPlaceholder" | "retryFromStage" | "videoPreview" | "downloadMp4" | "fallbackVideo" | "watermarkBadge" | "c2paBadge" | "finalExportBadge",
    string
  >>;
  readonly providers: Readonly<Record<
    | "testProvider" | "runtimeMissing" | "assetsMissing" | "notConfigured" | "notImplemented" | "requiresGpu" | "requiresNetwork" | "requiresModelFiles" | "providerStatus" | "testResult" | "addCustom" | "customName" | "customCategory" | "customBaseUrl" | "category" | "backendType" | "defaultModel" | "label" | "isLocal" | "notes" | "docsLink" | "warning" | "categoryLlm" | "categoryTts" | "categoryVideo" | "categoryAudioProcessor" | "categoryImageProcessor" | "selectProvider" | "noProviders" | "test1Title" | "test1Intro" | "diagnosticsRunning" | "diagnosticsOk" | "diagnosticsFailed" | "refreshCatalog" | "refreshAction" | "diagnosticsIntro" | "failedToLoad" | "videoReadinessFootnote" | "backendLabel" | "providersTitle" | "loadingProviders" | "addingProviderNote" | "defaultOption",
    string
  >>;
  readonly logs: Readonly<Record<
    | "title" | "exportJson" | "exportTxt" | "clearLogs" | "sessionLocal" | "logLevel" | "source" | "noEntries" | "filterByLevel" | "allLevels" | "filterCount" | "expand" | "collapse" | "info" | "warning" | "errorLevel" | "successLevel" | "sourceFrontend" | "sourceApi" | "sourceBackend" | "sourceSystem",
    string
  >>;
  readonly help: Readonly<Record<
    | "open" | "close" | "search" | "related" | "searchPlaceholder" | "noResults",
    string
  >>;
  readonly errors: Readonly<Record<
    | "script_provider_disabled" | "script_model_missing" | "script_provider_unreachable" | "script_generation_failed" | "tts_runtime_missing" | "tts_assets_missing" | "tts_generation_failed" | "tts_provider_not_configured" | "tts_provider_not_implemented" | "video_assets_missing" | "video_gpu_missing" | "video_runtime_missing" | "video_provider_not_configured" | "video_provider_not_implemented" | "video_face_landmark_missing" | "video_face_image_too_small" | "video_generation_failed" | "provider_not_implemented" | "provider_not_configured" | "artifact_not_found" | "upload_failed" | "validation_error" | "unknown",
    string
  >>;
  readonly videoRecovery: Readonly<Record<
    | "faceLandmarkMissingTitle"
    | "faceLandmarkMissingBody"
    | "faceImageTooSmallTitle"
    | "faceImageTooSmallBody"
    | "uploadClearPortrait"
    | "editAndReplaceImage"
    | "retryAfterEdit"
    | "portraitRequirements",
    string
  >>;
  readonly sidebar: Readonly<Record<
    "logs" | "backend" | "settings" | "test1" | "keys" | "services" | "activity" | "collapse" | "expand",
    string
  >>;
  readonly backendLogs: Readonly<Record<
    | "filterPlaceholder" | "pause" | "resume" | "reload" | "reloadHelp" | "clear" | "count" | "empty" | "emptyWaiting" | "emptyFiltered" | "emptyError",
    string
  >>;
  readonly characterVideos: Readonly<Record<
    | "empty" | "colCreated" | "colProvider" | "colDuration" | "colJobStatus" | "colJobLink",
    string
  >>;
  readonly artifactTable: Readonly<Record<
    | "header_type" | "header_id" | "header_mime" | "header_size" | "header_dim" | "header_sha" | "header_real" | "header_created" | "real_yes" | "real_no" | "real_metadata" | "real_manifest" | "empty",
    string
  >>;
  readonly qc: Readonly<Record<
    | "title" | "targetDuration" | "segments" | "script" | "editPlan" | "reelDraftUri" | "checksHeading" | "metadataOnlyNote" | "realMediaNote",
    string
  >>;
  readonly finalExportLabels: Readonly<Record<
    | "title" | "exportUri" | "exportType" | "targetDuration" | "watermarkRequired" | "c2paRequired" | "reelDraft" | "qcReport" | "note" | "noEncodedVideoNote",
    string
  >>;
  readonly recovery: Readonly<Record<
    | "title" | "terminalNote" | "terminalCancelDisabled" | "terminalRetryDisabled" | "retryFromStage" | "retryAvailable" | "retryNotAvailable" | "cancelReason" | "cancelReasonPlaceholder" | "retryReason" | "retryReasonPlaceholder" | "cancelHistory" | "retryHistory" | "lastError",
    string
  >>;
  readonly compliance: Readonly<Record<
    | "title" | "events" | "stage" | "decision" | "reason" | "createdAt" | "noEvents" | "extra",
    string
  >>;
  readonly customProviders: Readonly<Record<
    | "title" | "intro" | "add" | "edit" | "remove" | "providerId" | "category" | "label" | "baseUrl" | "isLocal" | "requiresGpu" | "requiresModelFiles" | "notes" | "save" | "cancel" | "noCustom" | "validationError" | "loading" | "metadataOnlyNote" | "providerIdSlugSafe" | "providerIdPlaceholder" | "backendType" | "backendTypePlaceholder" | "localityField" | "localityLocal" | "localityExternal" | "endpointUrlOptional" | "endpointUrlPlaceholder" | "defaultModelOptional" | "supportedModelsCsv" | "requiresNetwork" | "enabled" | "disabled" | "gpuRequiredFlag" | "addAction" | "deleteAria",
    string
  >>;
  readonly providersSection: Readonly<Record<
    | "title" | "intro" | "scriptDefault" | "ttsDefault" | "videoDefault" | "ttsTestTitle" | "ttsTestRunning" | "ttsTestSuccess" | "ttsTestFailure" | "providersLoading" | "providersFailed",
    string
  >>;
  readonly footer: Readonly<Record<
    "complianceLine" | "helpLink",
    string
  >>;
  readonly badges: Readonly<Record<
    | "gpuRequired" | "requiresNetwork" | "requiresModelFiles" | "customMetadataOnly" | "qcGate" | "aiDisclosureStatus" | "manifestOnly" | "realMp4" | "interfaceLanguage" | "openSettingsToChangeUrl" | "completedStages" | "currentStage" | "test1Description" | "uploadedImagePreview" | "uploadedAudioPreview" | "fillBriefFirst",
    string
  >>;
  readonly editJob: Readonly<Record<
    | "title" | "failedToLoad" | "updateRejected" | "editable" | "noChanges" | "saving" | "saveChanges" | "savingDone" | "lockedAfterCompliance" | "lockedTerminal" | "backToJob" | "readOnly" | "terminalNote" | "complianceLockedNote" | "briefLabel" | "targetDurationLabel" | "scriptTextLabel" | "loadingJob" | "publishedLockedNote" | "cannotEditCurrent" | "cannotEditThisJob" | "someFieldsLocked" | "providerChangeableBeforeRetry" | "providerEditIntro" | "saveBeforeRetry" | "retryAfterEdit" | "changesSaved" | "currentImage" | "replacementSelected",
    string
  >>;
  readonly uploadsPage: Readonly<Record<
    | "sectionText" | "sectionAudio" | "sectionImage" | "recentTab" | "noUploadsYet" | "localToTab" | "copyId" | "titleOptional" | "registerText" | "registering" | "scriptCannotBeEmpty" | "failedToLoadOptions" | "uploadAudioTitle" | "uploadImageTitle",
    string
  >>;
  readonly stageTimeline: Readonly<Record<
    | "completedStages" | "currentStage" | "failedStages" | "pendingStages" | "noStages" | "countCompleted" | "countFailed" | "countPending" | "noFailedStages" | "terminalPollingStopped" | "audioFitTitle" | "audioFitTarget" | "audioFitAudio" | "audioFitDelta",
    string
  >>;
  readonly recoveryHistory: Readonly<Record<
    | "cancelledAt" | "cancellationReason" | "retryRequestedAt" | "retryCount" | "lastError" | "history",
    string
  >>;
  readonly providerSelection: Readonly<Record<
    | "warningPrefix" | "warningSuffixCleanError" | "warningRequires" | "subtitleFormatSrt" | "subtitleFormatVtt",
    string
  >>;
  readonly statuses: Readonly<Record<
    | "pending_compliance" | "accepted" | "published" | "rejected" | "failed" | "running" | "succeeded" | "skipped" | "pending" | "cancelled"
    | "active" | "inactive" | "draft" | "editing" | "retired"
    | "unknown",
    string
  >>;
  readonly stages: Readonly<Record<
    | "policy_gate" | "scriptwriter" | "voice" | "face" | "identity_guard" | "pre_lipsync_auth" | "lipsync" | "editor" | "qc" | "publisher" | "export_disclosure_validation" | "compliance" | "completed" | "failed" | "pending" | "running",
    string
  >>;
  readonly artifactTypes: Readonly<Record<
    | "script" | "audio" | "image" | "video" | "final_export" | "qc_report" | "edit_plan" | "subtitle" | "manifest" | "metadata" | "unknown",
    string
  >>;
  readonly voiceModes: Readonly<Record<
    | "tts" | "provided_audio",
    string
  >>;
  readonly faceModes: Readonly<Record<
    | "provided_image" | "none",
    string
  >>;
  readonly providerStatuses: Readonly<Record<
    | "available" | "configured" | "not_configured" | "not_implemented" | "disabled" | "error" | "unknown",
    string
  >>;
  readonly runtime: Readonly<Record<
    | "audioFitOk" | "audioFitTooShort" | "audioFitTooLong" | "audioFitMissingAudio" | "audioFitLabel" | "audioFitRecAccept" | "audioFitRecRegenScriptShorter" | "audioFitRecRegenScriptLonger" | "audioFitRecAdjustDuration" | "audioFitRecUploadBetterAudio" | "qcDecisionPass" | "qcDecisionFail" | "qcDecisionWarn" | "audioFitStatus" | "audioFitMeta",
    string
  >>;
  readonly validation: Readonly<Record<
    | "required" | "invalidType" | "valueTooShort" | "valueTooLong" | "invalidEnum" | "syntheticPersonRequired" | "consentRequired" | "scriptTextRequiredForTts" | "targetDurationRange" | "providerSelectionInvalidKey" | "unknownJob" | "backendUnavailable" | "httpError" | "extraForbiddenField" | "watermarkRequiredTrue" | "c2paRequiredTrue" | "languageNotSupported",
    string
  >>;
  readonly time: Readonly<Record<
    | "justNow" | "secondsAgo" | "minutesAgo" | "hoursAgo" | "daysAgo",
    string
  >>;
  readonly progressBar: Readonly<Record<
    | "ariaLabel" | "stagesUnit" | "failedSuffix",
    string
  >>;
  readonly logsPanel: Readonly<Record<
    | "showDetails" | "hideDetails" | "exportedFormat",
    string
  >>;
  readonly uploadCard: Readonly<Record<
    | "fileTooLarge" | "unsupportedExtension" | "selectedFileSize" | "currentArtifactShort" | "maxFileSizeLabel",
    string
  >>;
  readonly complianceList: Readonly<Record<
    | "empty",
    string
  >>;
  readonly niceErrors: Readonly<Record<
    | "piper_runtime_missing" | "piper_assets_missing" | "piper_provider_not_configured" | "piper_provider_not_implemented" | "piper_generation_failed" | "f5_runtime_missing" | "f5_assets_missing" | "f5_provider_not_configured" | "f5_provider_not_implemented" | "f5_generation_failed" | "provider_disabled",
    string
  >>;
  // Phase 12 — Characters / Personas (top-level keys carry flat strings,
  // ``sections`` / ``fields`` / ``actions`` / ``images`` / ``summary`` /
  // ``help`` are nested string maps so we don't have to enumerate ~80
  // field names in this type. The parity test enforces leaf-key equality
  // between en.ts and ro.ts at runtime.
  readonly characters: {
    readonly title: string;
    readonly pageHelp: string;
    readonly addNew: string;
    readonly empty: string;
    readonly nameLabel: string;
    readonly displayNameLabel: string;
    readonly slugLabel: string;
    readonly statusLabel: string;
    readonly languageLabel: string;
    readonly voiceProviderLabel: string;
    readonly imageProviderLabel: string;
    readonly mainReferenceLabel: string;
    readonly imagesCount: string;
    readonly videosCount: string;
    readonly version: string;
    readonly deleteConfirmTitle: string;
    readonly deleteConfirmBody: string;
    readonly actions: Readonly<Record<string, string>>;
    readonly sections: Readonly<Record<string, string>>;
    readonly fields: Readonly<Record<string, string>>;
    readonly images: Readonly<Record<string, string>>;
    readonly summary: Readonly<Record<string, string>>;
    readonly help: Readonly<Record<string, string>>;
    // Phase 23 — character lifecycle (editing / active / retired).
    readonly lifecycle: Readonly<Record<string, string>>;
    // Phase IG-4 — identity-consistent generation panel.
    readonly identity: Readonly<Record<string, string>>;
  };
  readonly characterLookups: Readonly<Record<
    string,
    Readonly<Record<string, string>>
  >>;
  readonly providerStatus: Readonly<Record<string, string>>;
  readonly videoCharacter: Readonly<Record<string, string>>;
  // Phase 12X — DB-backed API keys store displayed in the right-sidebar
  // "Keys" tab.
  readonly keys: {
    readonly title: string;
    readonly intro: string;
    readonly placeholder: string;
    readonly save: string;
    readonly test: string;
    readonly probe: string;
    readonly confirmDelete: string;
    readonly categories: Readonly<Record<string, string>>;
  };
}
