// Settings types + persistence helpers.
//
// Settings live in localStorage so the operator can switch the backend URL
// at runtime without rebuilding the frontend. NEXT_PUBLIC_API_BASE_URL is
// only the default; the Settings tab overrides it.

export interface Settings {
  readonly apiBaseUrl: string;
  readonly apiBaseUrlIsCustom: boolean;
  readonly frontendUrl: string;
  readonly pollingIntervalSeconds: number;
  readonly autoPollingEnabled: boolean;
  readonly showBackendLogs: boolean;
  readonly showFrontendLogs: boolean;
  readonly showApiLogs: boolean;
  readonly showSystemLogs: boolean;
  readonly maxLogEntries: number;
  // Docker Compose light-runtime host ports. Editing them in the UI does
  // not restart Docker; the values guide the API base URL and the copy-
  // ready compose-up command shown in Settings.
  readonly backendHostPort: number;
  readonly frontendHostPort: number;
  readonly postgresHostPort: number;
  readonly redisHostPort: number;
  readonly minioHostPort: number;
  // Operator-side defaults applied to the create-job form.
  readonly defaultTargetDurationSeconds: number;
  readonly defaultVoiceMode: "tts" | "provided_audio";
  readonly defaultFaceModeEnabled: boolean;
  // Phase 4F: per-category default providers used to prefill the
  // create-job + edit-job forms. ``null`` means "use backend default".
  readonly defaultLlmProvider: string | null;
  readonly defaultTtsProvider: string | null;
  readonly defaultVideoProvider: string | null;
}

const DEFAULT_API_BASE_URL =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL) ||
  "http://localhost:8000";

const DEFAULT_FRONTEND_URL =
  typeof window !== "undefined" ? window.location.origin : "http://localhost:3000";

export const DEFAULT_SETTINGS: Settings = {
  apiBaseUrl: DEFAULT_API_BASE_URL,
  apiBaseUrlIsCustom: false,
  frontendUrl: DEFAULT_FRONTEND_URL,
  pollingIntervalSeconds: 3,
  autoPollingEnabled: true,
  showBackendLogs: true,
  showFrontendLogs: true,
  showApiLogs: true,
  showSystemLogs: true,
  maxLogEntries: 500,
  backendHostPort: 8000,
  frontendHostPort: 3000,
  postgresHostPort: 5432,
  redisHostPort: 6379,
  minioHostPort: 9000,
  defaultTargetDurationSeconds: 30,
  defaultVoiceMode: "tts",
  defaultFaceModeEnabled: false,
  defaultLlmProvider: null,
  defaultTtsProvider: null,
  defaultVideoProvider: null,
};

function clampPort(n: unknown, fallback: number): number {
  const v = Number(n);
  if (Number.isFinite(v) && v >= 1 && v <= 65535) return Math.floor(v);
  return fallback;
}

export const SETTINGS_STORAGE_KEY = "aivideo:settings:v1";
export const SIDEBAR_STORAGE_KEY = "aivideo:sidebar:v1";

export interface SidebarState {
  readonly collapsed: boolean;
  readonly activeTab: "logs" | "settings";
}

export const DEFAULT_SIDEBAR_STATE: SidebarState = {
  collapsed: false,
  activeTab: "logs",
};

export function loadSettings(): Settings {
  if (typeof window === "undefined") return DEFAULT_SETTINGS;
  try {
    const raw = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    const parsed = JSON.parse(raw) as Partial<Settings>;
    return mergeSettings(parsed);
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function saveSettings(settings: Settings): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
  } catch {
    // localStorage write can fail (quota, private mode); ignore.
  }
}

export function loadSidebarState(): SidebarState {
  if (typeof window === "undefined") return DEFAULT_SIDEBAR_STATE;
  try {
    const raw = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
    if (!raw) return DEFAULT_SIDEBAR_STATE;
    const parsed = JSON.parse(raw) as Partial<SidebarState>;
    return {
      collapsed: typeof parsed.collapsed === "boolean" ? parsed.collapsed : DEFAULT_SIDEBAR_STATE.collapsed,
      activeTab:
        parsed.activeTab === "logs" || parsed.activeTab === "settings"
          ? parsed.activeTab
          : DEFAULT_SIDEBAR_STATE.activeTab,
    };
  } catch {
    return DEFAULT_SIDEBAR_STATE;
  }
}

export function saveSidebarState(state: SidebarState): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // ignore
  }
}

function mergeSettings(partial: Partial<Settings>): Settings {
  const voiceMode: Settings["defaultVoiceMode"] =
    partial.defaultVoiceMode === "provided_audio" ? "provided_audio" : "tts";
  return {
    apiBaseUrl:
      typeof partial.apiBaseUrl === "string" && partial.apiBaseUrl
        ? partial.apiBaseUrl
        : DEFAULT_SETTINGS.apiBaseUrl,
    apiBaseUrlIsCustom:
      typeof partial.apiBaseUrlIsCustom === "boolean"
        ? partial.apiBaseUrlIsCustom
        : DEFAULT_SETTINGS.apiBaseUrlIsCustom,
    frontendUrl:
      typeof partial.frontendUrl === "string" && partial.frontendUrl
        ? partial.frontendUrl
        : DEFAULT_SETTINGS.frontendUrl,
    pollingIntervalSeconds:
      typeof partial.pollingIntervalSeconds === "number" &&
      partial.pollingIntervalSeconds >= 1 &&
      partial.pollingIntervalSeconds <= 600
        ? partial.pollingIntervalSeconds
        : DEFAULT_SETTINGS.pollingIntervalSeconds,
    autoPollingEnabled:
      typeof partial.autoPollingEnabled === "boolean"
        ? partial.autoPollingEnabled
        : DEFAULT_SETTINGS.autoPollingEnabled,
    showBackendLogs:
      typeof partial.showBackendLogs === "boolean"
        ? partial.showBackendLogs
        : DEFAULT_SETTINGS.showBackendLogs,
    showFrontendLogs:
      typeof partial.showFrontendLogs === "boolean"
        ? partial.showFrontendLogs
        : DEFAULT_SETTINGS.showFrontendLogs,
    showApiLogs:
      typeof partial.showApiLogs === "boolean"
        ? partial.showApiLogs
        : DEFAULT_SETTINGS.showApiLogs,
    showSystemLogs:
      typeof partial.showSystemLogs === "boolean"
        ? partial.showSystemLogs
        : DEFAULT_SETTINGS.showSystemLogs,
    maxLogEntries:
      typeof partial.maxLogEntries === "number" &&
      partial.maxLogEntries >= 50 &&
      partial.maxLogEntries <= 5000
        ? Math.floor(partial.maxLogEntries)
        : DEFAULT_SETTINGS.maxLogEntries,
    backendHostPort: clampPort(partial.backendHostPort, DEFAULT_SETTINGS.backendHostPort),
    frontendHostPort: clampPort(partial.frontendHostPort, DEFAULT_SETTINGS.frontendHostPort),
    postgresHostPort: clampPort(partial.postgresHostPort, DEFAULT_SETTINGS.postgresHostPort),
    redisHostPort: clampPort(partial.redisHostPort, DEFAULT_SETTINGS.redisHostPort),
    minioHostPort: clampPort(partial.minioHostPort, DEFAULT_SETTINGS.minioHostPort),
    defaultTargetDurationSeconds:
      typeof partial.defaultTargetDurationSeconds === "number" &&
      partial.defaultTargetDurationSeconds >= 1 &&
      partial.defaultTargetDurationSeconds <= 600
        ? Math.floor(partial.defaultTargetDurationSeconds)
        : DEFAULT_SETTINGS.defaultTargetDurationSeconds,
    defaultVoiceMode: voiceMode,
    defaultFaceModeEnabled:
      typeof partial.defaultFaceModeEnabled === "boolean"
        ? partial.defaultFaceModeEnabled
        : DEFAULT_SETTINGS.defaultFaceModeEnabled,
    defaultLlmProvider:
      typeof partial.defaultLlmProvider === "string" && partial.defaultLlmProvider
        ? partial.defaultLlmProvider
        : DEFAULT_SETTINGS.defaultLlmProvider,
    defaultTtsProvider:
      typeof partial.defaultTtsProvider === "string" && partial.defaultTtsProvider
        ? partial.defaultTtsProvider
        : DEFAULT_SETTINGS.defaultTtsProvider,
    defaultVideoProvider:
      typeof partial.defaultVideoProvider === "string" && partial.defaultVideoProvider
        ? partial.defaultVideoProvider
        : DEFAULT_SETTINGS.defaultVideoProvider,
  };
}

// Read the active API base URL directly from localStorage. Used by the
// fetch wrapper in lib/api.ts so each request picks up the latest override
// without requiring a React render to flow values through.
export function getActiveApiBaseUrl(): string {
  if (typeof window === "undefined") return DEFAULT_API_BASE_URL;
  try {
    const raw = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<Settings>;
      if (typeof parsed.apiBaseUrl === "string" && parsed.apiBaseUrl) {
        return parsed.apiBaseUrl;
      }
    }
  } catch {
    // ignore
  }
  return DEFAULT_API_BASE_URL;
}
