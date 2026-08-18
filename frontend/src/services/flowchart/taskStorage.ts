const STORAGE_NAMESPACE = 'flowchart-toolbox';
const ACTIVE_TASK_ID_KEY = `${STORAGE_NAMESPACE}:active-task-id`;
const ACTIVE_DOCUMENT_ID_KEY = `${STORAGE_NAMESPACE}:active-document-id`;
const BROWSER_SESSION_ID_KEY = `${STORAGE_NAMESPACE}:browser-session-id`;

let volatileSessionId: string | null = null;

export interface StoredTaskContext {
  taskId: string | null;
  documentId: string | null;
}

function getStorage(): Storage | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function getSessionStorage(): Storage | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function createSessionId(): string {
  if (
    typeof crypto !== 'undefined' &&
    typeof crypto.randomUUID === 'function'
  ) {
    return crypto.randomUUID();
  }
  return `session-${Date.now().toString(36)}-${Math.random()
    .toString(36)
    .slice(2)}`;
}

export function restoreTaskContext(): StoredTaskContext {
  const storage = getStorage();
  return {
    taskId: storage?.getItem(ACTIVE_TASK_ID_KEY) || null,
    documentId: storage?.getItem(ACTIVE_DOCUMENT_ID_KEY) || null,
  };
}

export function saveActiveTaskId(taskId: string): void {
  getStorage()?.setItem(ACTIVE_TASK_ID_KEY, taskId);
}

export function clearActiveTaskId(): void {
  getStorage()?.removeItem(ACTIVE_TASK_ID_KEY);
}

export function saveActiveDocumentId(documentId: string): void {
  getStorage()?.setItem(ACTIVE_DOCUMENT_ID_KEY, documentId);
}

/**
 * 同一浏览器会话内的关联标识。它只辅助任务恢复，后端仍以登录用户为授权边界。
 */
export function getOrCreateFlowchartSessionId(): string {
  const storage = getSessionStorage();
  const stored = storage?.getItem(BROWSER_SESSION_ID_KEY);
  if (stored) {
    return stored;
  }
  if (volatileSessionId) {
    return volatileSessionId;
  }

  volatileSessionId = createSessionId();
  storage?.setItem(BROWSER_SESSION_ID_KEY, volatileSessionId);
  return volatileSessionId;
}
