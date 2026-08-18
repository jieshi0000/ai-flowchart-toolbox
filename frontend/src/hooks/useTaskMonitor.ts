import {
  FlowchartTask,
  FlowchartTaskStatus,
  getFlowchartTask,
} from '@/services/flowchart/task';
import {
  clearActiveTaskId,
  saveActiveDocumentId,
  saveActiveTaskId,
} from '@/services/flowchart/taskStorage';
import { useEffect, useRef, useState } from 'react';

const POLLING_INTERVAL_MS = 2_000;
const SSE_INACTIVITY_MS = 30_000;

const TERMINAL_TASK_STATUSES = new Set<FlowchartTaskStatus>([
  'success',
  'failed',
  'canceled',
  'expired',
]);

export type TaskConnectionMode = 'idle' | 'connecting' | 'sse' | 'polling';

export interface UseTaskMonitorOptions {
  taskId: string | null;
  enabled?: boolean;
  onTaskChange?: (task: FlowchartTask) => void;
}

export interface TaskMonitorResult {
  task: FlowchartTask | null;
  connectionMode: TaskConnectionMode;
}

export function isTerminalTaskStatus(status: FlowchartTaskStatus): boolean {
  return TERMINAL_TASK_STATUSES.has(status);
}

export function useTaskMonitor({
  taskId,
  enabled = true,
  onTaskChange,
}: UseTaskMonitorOptions): TaskMonitorResult {
  const [task, setTask] = useState<FlowchartTask | null>(null);
  const [connectionMode, setConnectionMode] =
    useState<TaskConnectionMode>('idle');
  const onTaskChangeRef = useRef(onTaskChange);

  useEffect(() => {
    onTaskChangeRef.current = onTaskChange;
  }, [onTaskChange]);

  useEffect(() => {
    if (!enabled || !taskId) {
      setTask(null);
      setConnectionMode('idle');
      return undefined;
    }

    let disposed = false;
    let pollingStarted = false;
    let terminal = false;
    let pollTimer: number | undefined;
    const sseAbortController = new AbortController();
    saveActiveTaskId(taskId);

    const applyTask = (nextTask: FlowchartTask) => {
      if (disposed) {
        return;
      }
      setTask(nextTask);
      if (nextTask.documentId) {
        saveActiveDocumentId(nextTask.documentId);
      }
      if (isTerminalTaskStatus(nextTask.status)) {
        terminal = true;
        setConnectionMode('idle');
        clearActiveTaskId();
        if (pollTimer !== undefined) {
          window.clearInterval(pollTimer);
          pollTimer = undefined;
        }
        sseAbortController.abort();
      }
      onTaskChangeRef.current?.(nextTask);
    };

    const refreshTask = async () => {
      try {
        const result = await getFlowchartTask(taskId);
        if (result.code !== 200 || !result.data) {
          return;
        }
        applyTask(result.data);
      } catch {
        // 网络错误保持最近状态；轮询或下一次 SSE 重连继续恢复。
      }
    };

    const startPolling = () => {
      if (disposed || terminal || pollingStarted) {
        return;
      }
      pollingStarted = true;
      sseAbortController.abort();
      setConnectionMode('polling');
      void refreshTask();
      pollTimer = window.setInterval(() => {
        void refreshTask();
      }, POLLING_INTERVAL_MS);
    };

    const consumeSse = async () => {
      try {
        let token: string | null = null;
        try {
          token = window.localStorage.getItem('token');
        } catch {
          token = null;
        }
        const response = await fetch(
          `/api/flowchart/tasks/events?taskId=${encodeURIComponent(taskId)}`,
          {
            signal: sseAbortController.signal,
            headers: {
              Accept: 'text/event-stream',
              ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
          },
        );
        if (!response.ok || !response.body) {
          throw new Error('任务事件流不可用');
        }

        setConnectionMode('sse');
        let lastTaskEventAt = Date.now();
        let buffer = '';
        const decoder = new TextDecoder();
        const inactivityTimer = window.setInterval(() => {
          if (Date.now() - lastTaskEventAt >= SSE_INACTIVITY_MS) {
            startPolling();
          }
        }, 1_000);

        try {
          const reader = response.body.getReader();
          while (!disposed && !terminal) {
            const { done, value } = await reader.read();
            if (done) {
              break;
            }
            buffer += decoder.decode(value, { stream: true });
            const frames = buffer.replace(/\r\n/g, '\n').split('\n\n');
            buffer = frames.pop() || '';
            for (const frame of frames) {
              const event = parseTaskStatusEvent(frame);
              if (!event) {
                continue;
              }
              lastTaskEventAt = Date.now();
              applyTask(event);
            }
          }
        } finally {
          window.clearInterval(inactivityTimer);
        }
      } catch {
        if (sseAbortController.signal.aborted) {
          return;
        }
      }

      startPolling();
    };

    setTask(null);
    setConnectionMode('connecting');
    void refreshTask();
    void consumeSse();

    return () => {
      disposed = true;
      sseAbortController.abort();
      if (pollTimer !== undefined) {
        window.clearInterval(pollTimer);
      }
    };
  }, [enabled, taskId]);

  return { task, connectionMode };
}

function parseTaskStatusEvent(frame: string): FlowchartTask | null {
  const lines = frame.split('\n');
  const eventName = lines
    .find((line) => line.startsWith('event:'))
    ?.slice(6)
    .trim();
  if (eventName !== 'task-status') {
    return null;
  }
  const data = lines
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n');
  if (!data) {
    return null;
  }
  try {
    const event = JSON.parse(data) as Partial<FlowchartTask>;
    if (
      typeof event.taskId !== 'string' ||
      typeof event.status !== 'string' ||
      typeof event.progress !== 'number'
    ) {
      return null;
    }
    return event as FlowchartTask;
  } catch {
    return null;
  }
}
