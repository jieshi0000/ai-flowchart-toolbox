const STORAGE_NAMESPACE = 'flowchart-toolbox';
const ACTIVE_TASK_ID_KEY = `${STORAGE_NAMESPACE}:active-task-id`;
const ACTIVE_DOCUMENT_ID_KEY = `${STORAGE_NAMESPACE}:active-document-id`;

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
