import { useLeaveConfirmation } from '@/hooks/useLeaveConfirmation';
import { isTerminalTaskStatus, useTaskMonitor } from '@/hooks/useTaskMonitor';
import {
  AUTO_ROUTE_MODEL,
  createEmptyDiagramData,
  isDiagramDirty,
  useFlowchartWorkbenchStore,
  type DiagramData,
  type DiagramNode,
} from '@/models/flowchart';
import {
  createFlowchartDocumentExport,
  deleteFlowchartDocument,
  downloadFlowchartFile,
  getFlowchartDocument,
  listFlowchartDocuments,
  saveFlowchartDocument,
  type FlowchartDocument,
  type FlowchartExportFormat,
  type FlowchartDocumentHistoryItem,
} from '@/services/flowchart/document';
import {
  cancelFlowchartTask,
  createFlowchartTask,
  FlowchartTask,
  FlowchartTaskStatus,
  listRecoverableFlowchartTasks,
  retryFlowchartTask,
} from '@/services/flowchart/task';
import {
  clearActiveDocumentId,
  clearActiveTaskId,
  getOrCreateFlowchartSessionId,
  restoreTaskContext,
  saveActiveDocumentId,
} from '@/services/flowchart/taskStorage';
import {
  FlowchartProvider,
  type FlowchartDiagramTheme,
  getFlowchartProviders,
  getFlowchartTemplates,
} from '@/services/flowchart/workbench';
import {
  ApartmentOutlined,
  CheckCircleFilled,
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  ExportOutlined,
  FileTextOutlined,
  LoadingOutlined,
  PlusOutlined,
  UploadOutlined,
  ClockCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SaveOutlined,
  SendOutlined,
  StopOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Badge,
  Button,
  Empty,
  Input,
  message,
  Modal,
  Popconfirm,
  Segmented,
  Select,
  Spin,
  Switch,
  Tooltip,
  Typography,
} from 'antd';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useStore } from 'zustand';
import DiagramCanvas from './components/DiagramCanvas';
import { createUniqueNodeId, layoutDiagramData } from './components/diagramFlow';
import { MermaidDiagram } from './components/MermaidDiagram';
import { MermaidPanel } from './components/MermaidPanel';
import { NodePropertyPanel } from './components/NodePropertyPanel';
import styles from './index.less';

type BadgeStatus = 'default' | 'error' | 'processing' | 'success' | 'warning';

interface TaskPresentation {
  badge: BadgeStatus;
  label: string;
  description: string;
}

interface RequestFailure {
  errorCode?: string | number | null;
  message?: string | null;
}

type DiagramTheme = FlowchartDiagramTheme;
const DIAGRAM_THEME_STYLES: Record<DiagramTheme, Record<DiagramNode['type'], { fill: string; stroke: string }>> = {
  blue: {
    start: { fill: '#eef5ff', stroke: '#8eb8ff' }, end: { fill: '#edf3ff', stroke: '#8eb8ff' }, process: { fill: '#eef5ff', stroke: '#b9d2ff' }, decision: { fill: '#fff8e7', stroke: '#e9c77a' }, input_output: { fill: '#eef7fb', stroke: '#9ccfe5' }, subprocess: { fill: '#f3f0ff', stroke: '#c8baf5' },
  },
  purple: {
    start: { fill: '#f3f0ff', stroke: '#b7a8f0' }, end: { fill: '#f3f0ff', stroke: '#b7a8f0' }, process: { fill: '#f5f1ff', stroke: '#d3c7ff' }, decision: { fill: '#fff8e7', stroke: '#e9c77a' }, input_output: { fill: '#f1f4ff', stroke: '#b8c6f1' }, subprocess: { fill: '#f7efff', stroke: '#d9bdf5' },
  },
  green: {
    start: { fill: '#eafaf4', stroke: '#8ed3b6' }, end: { fill: '#eafaf4', stroke: '#8ed3b6' }, process: { fill: '#edfbf5', stroke: '#b5e3d0' }, decision: { fill: '#fff8e7', stroke: '#e9c77a' }, input_output: { fill: '#eefaf8', stroke: '#9fd8cf' }, subprocess: { fill: '#f0f8f4', stroke: '#b8ddc8' },
  },
};

const TASK_PRESENTATIONS: Record<FlowchartTaskStatus, TaskPresentation> = {
  waiting: {
    badge: 'processing',
    label: '任务已排队',
    description: '正在等待任务处理',
  },
  submitting: {
    badge: 'processing',
    label: '正在提交',
    description: '正在连接模型服务',
  },
  provider_queued: {
    badge: 'processing',
    label: '任务已排队',
    description: '正在等待模型处理',
  },
  provider_processing: {
    badge: 'processing',
    label: '正在生成流程图',
    description: '模型正在处理描述',
  },
  validating: {
    badge: 'processing',
    label: '正在校验流程图结构',
    description: '正在检查节点与连线',
  },
  rendering: {
    badge: 'processing',
    label: '正在渲染流程图',
    description: '正在准备生成结果',
  },
  success: {
    badge: 'success',
    label: '流程图已生成',
    description: '生成任务已完成',
  },
  failed: {
    badge: 'error',
    label: '生成失败',
    description: '请根据提示调整描述后重试',
  },
  canceled: {
    badge: 'warning',
    label: '任务已取消',
    description: '可修改描述后再次生成',
  },
  expired: {
    badge: 'warning',
    label: '任务已过期',
    description: '请重新创建生成任务',
  },
};

const EXPORT_TASK_PRESENTATIONS: Record<FlowchartTaskStatus, TaskPresentation> =
  {
    ...TASK_PRESENTATIONS,
    waiting: {
      badge: 'processing',
      label: '导出已排队',
      description: '正在等待导出 Worker',
    },
    rendering: {
      badge: 'processing',
      label: '正在渲染导出文件',
      description: 'Chromium 正在准备文件',
    },
    success: {
      badge: 'success',
      label: '导出已完成',
      description: '导出文件已准备就绪',
    },
    failed: {
      badge: 'error',
      label: '导出失败',
      description: '请稍后重试导出',
    },
  };

const CANCELLABLE_TASK_STATUSES = new Set<FlowchartTaskStatus>([
  'waiting',
  'submitting',
  'provider_queued',
  'provider_processing',
]);

const HISTORY_PAGE_SIZE = 20;

function createIdempotencyKey(): string {
  if (
    typeof crypto !== 'undefined' &&
    typeof crypto.randomUUID === 'function'
  ) {
    return crypto.randomUUID();
  }
  return `request-${Date.now().toString(36)}-${Math.random()
    .toString(36)
    .slice(2)}`;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object'
    ? (value as Record<string, unknown>)
    : null;
}

function requestFailureFromString(value: string): RequestFailure {
  const trimmed = value.trim();
  if (!trimmed) {
    return {};
  }

  try {
    const parsed = JSON.parse(trimmed) as unknown;
    if (parsed && typeof parsed === 'object') {
      return requestFailureFrom(parsed);
    }
  } catch {
    // Umi may serialize the business response as {code:...,errorCode:...}.
  }

  const errorCode = trimmed.match(
    /(?:errorCode|error_code)\s*[:=]\s*["']?([A-Za-z0-9_-]+)/i,
  )?.[1];
  const numericCode = trimmed.match(
    /(?:^|[,{\s])code\s*[:=]\s*["']?(\d{3,5})/i,
  )?.[1];
  const message = trimmed
    .match(/(?:^|[,{\s])message\s*[:=]\s*["']?([^,}]+?)["']?(?:[,}]|$)/i)?.[1]
    ?.trim();

  return {
    errorCode: errorCode || numericCode,
    message: message || (trimmed === '[object Object]' ? undefined : trimmed),
  };
}

function requestFailureFrom(error: unknown): RequestFailure {
  if (typeof error === 'string') {
    return requestFailureFromString(error);
  }
  const errorRecord = asRecord(error);
  const response = asRecord(errorRecord?.response);
  const responseData = asRecord(response?.data);
  const payload = asRecord(errorRecord?.data);
  const candidates = [errorRecord, payload, response, responseData].filter(
    (value): value is Record<string, unknown> => value !== null,
  );
  const errorCode = candidates
    .map((value) => value.errorCode)
    .find(
      (value): value is string | number =>
        typeof value === 'string' || typeof value === 'number',
    );
  const message = candidates
    .map((value) => value.message ?? value.errorMessage)
    .find((value): value is string => typeof value === 'string');
  return {
    errorCode,
    message,
  };
}

function friendlyTaskMessage(
  errorCode?: string | number | null,
  message?: string | null,
): string {
  const normalizedCode =
    typeof errorCode === 'string'
      ? errorCode.toUpperCase()
      : String(errorCode ?? '');
  const normalizedMessage = message?.toLowerCase() || '';
  switch (normalizedCode) {
    case 'PROVIDER_UNAVAILABLE':
    case '502':
      return '上游服务繁忙，请稍后重试';
    case 'PROVIDER_UNHEALTHY':
    case '503':
      return '当前默认供应商暂不可用，请稍后重试';
    case 'PROVIDER_RATE_LIMITED':
    case '429':
      return '当前生成请求较多，请稍后重试';
    case 'PROVIDER_NOT_CONFIGURED':
    case 'PROVIDER_AUTH_FAILED':
    case 'PROVIDER_SUBMIT_FAILED':
    case 'PROVIDER_POLL_FAILED':
      return '请检查网络连接或服务端配置';
    case 'TASK_CANCELED':
      return '任务已取消';
    case 'TASK_EXPIRED':
      return '任务已过期，请重新生成';
    default:
      if (
        normalizedMessage.includes('provider_unavailable') ||
        normalizedMessage.includes('provider unavailable')
      ) {
        return '上游服务繁忙，请稍后重试';
      }
      return message || '请检查网络连接或服务端配置';
  }
}

function friendlyFailureFrom(value: unknown): string {
  const failure = requestFailureFrom(value);
  return friendlyTaskMessage(failure.errorCode, failure.message);
}

function getConnectionLabel(
  mode: ReturnType<typeof useTaskMonitor>['connectionMode'],
  hasTask = false,
): string {
  switch (mode) {
    case 'connecting':
      return '正在连接任务状态';
    case 'sse':
      return '任务状态实时更新中';
    case 'polling':
      return '正在定时获取任务状态';
    default:
      return hasTask ? '任务状态已结束' : '等待生成任务';
  }
}

function diagramDataFromDocument(document: FlowchartDocument): DiagramData {
  const data: DiagramData = {
    id: document.id,
    title: document.title,
    direction: document.direction,
    nodes: document.nodes,
    edges: document.edges,
  };
  // 模型生成节点只提供语义结构时，位置默认都会是 0,0。首个版本进入
  // 工作台前统一完成一次 dagre 布局；后续已保存的手工坐标保持不变。
  return document.metadata.version === 1 ? layoutDiagramData(data) : data;
}

function applyDiagramTheme(data: DiagramData, theme: DiagramTheme): DiagramData {
  const palette = DIAGRAM_THEME_STYLES[theme];
  return {
    ...data,
    nodes: data.nodes.map((node) => ({
      ...node,
      style: { ...palette[node.type] },
    })),
  };
}

function providerStatusLabel(provider: FlowchartProvider): string {
  if (provider.status === 'healthy') {
    return '可用';
  }
  if (provider.status === 'rate_limited') {
    return '繁忙';
  }
  return '暂不可用';
}

const FlowchartWorkbench: React.FC = () => {
  const prompt = useFlowchartWorkbenchStore((state) => state.prompt);
  const direction = useFlowchartWorkbenchStore((state) => state.direction);
  const detailLevel = useFlowchartWorkbenchStore((state) => state.detailLevel);
  const thinkingEnabled = useFlowchartWorkbenchStore(
    (state) => state.thinkingEnabled,
  );
  const selectedModel = useFlowchartWorkbenchStore(
    (state) => state.selectedModel,
  );
  const activeTaskId = useFlowchartWorkbenchStore(
    (state) => state.activeTaskId,
  );
  const task = useFlowchartWorkbenchStore((state) => state.task);
  const providers = useFlowchartWorkbenchStore((state) => state.providers);
  const templates = useFlowchartWorkbenchStore((state) => state.templates);
  const providerLoadState = useFlowchartWorkbenchStore(
    (state) => state.providerLoadState,
  );
  const templateLoadState = useFlowchartWorkbenchStore(
    (state) => state.templateLoadState,
  );
  const providerNoticeDismissed = useFlowchartWorkbenchStore(
    (state) => state.providerNoticeDismissed,
  );
  const diagramData = useFlowchartWorkbenchStore((state) => state.diagramData);
  const documentVersion = useFlowchartWorkbenchStore(
    (state) => state.documentVersion,
  );
  const selectedElement = useFlowchartWorkbenchStore(
    (state) => state.selectedElement,
  );
  const mermaidSource = useFlowchartWorkbenchStore(
    (state) => state.mermaidSource,
  );
  const mermaidStatus = useFlowchartWorkbenchStore(
    (state) => state.mermaidStatus,
  );
  const mermaidError = useFlowchartWorkbenchStore(
    (state) => state.mermaidError,
  );
  const hasUnsavedChanges = useFlowchartWorkbenchStore(isDiagramDirty);
  const setPrompt = useFlowchartWorkbenchStore((state) => state.setPrompt);
  const setDirection = useFlowchartWorkbenchStore(
    (state) => state.setDirection,
  );
  const setDetailLevel = useFlowchartWorkbenchStore(
    (state) => state.setDetailLevel,
  );
  const setThinkingEnabled = useFlowchartWorkbenchStore(
    (state) => state.setThinkingEnabled,
  );
  const setSelectedModel = useFlowchartWorkbenchStore(
    (state) => state.setSelectedModel,
  );
  const setActiveTaskId = useFlowchartWorkbenchStore(
    (state) => state.setActiveTaskId,
  );
  const setTask = useFlowchartWorkbenchStore((state) => state.setTask);
  const setProviders = useFlowchartWorkbenchStore(
    (state) => state.setProviders,
  );
  const setTemplates = useFlowchartWorkbenchStore(
    (state) => state.setTemplates,
  );
  const setProviderLoadState = useFlowchartWorkbenchStore(
    (state) => state.setProviderLoadState,
  );
  const setTemplateLoadState = useFlowchartWorkbenchStore(
    (state) => state.setTemplateLoadState,
  );
  const dismissProviderNotice = useFlowchartWorkbenchStore(
    (state) => state.dismissProviderNotice,
  );
  const setDiagramData = useFlowchartWorkbenchStore(
    (state) => state.setDiagramData,
  );
  const resetDiagram = useFlowchartWorkbenchStore(
    (state) => state.resetDiagram,
  );
  const setDocumentVersion = useFlowchartWorkbenchStore(
    (state) => state.setDocumentVersion,
  );
  const markDiagramSaved = useFlowchartWorkbenchStore(
    (state) => state.markDiagramSaved,
  );
  const setMermaidPreview = useFlowchartWorkbenchStore(
    (state) => state.setMermaidPreview,
  );
  const setSelectedElement = useFlowchartWorkbenchStore(
    (state) => state.setSelectedElement,
  );
  const [isCreating, setIsCreating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [submissionError, setSubmissionError] = useState<string | null>(null);
  const [documentActionError, setDocumentActionError] = useState<string | null>(
    null,
  );
  const [activeMode, setActiveMode] = useState<
    'generate' | 'edit' | 'mermaid' | 'export'
  >('generate');
  const [diagramTheme, setDiagramTheme] = useState<DiagramTheme>('blue');
  const [exportFormat, setExportFormat] =
    useState<FlowchartExportFormat>('SVG');
  const [exportBackground, setExportBackground] = useState<
    'transparent' | 'white'
  >('transparent');
  const [isExporting, setIsExporting] = useState(false);
  const [exportActionError, setExportActionError] = useState<string | null>(
    null,
  );
  const [historyRecords, setHistoryRecords] = useState<
    FlowchartDocumentHistoryItem[]
  >([]);
  const [historyHasMore, setHistoryHasMore] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [deletingDocumentId, setDeletingDocumentId] = useState<string | null>(
    null,
  );
  const restoreStarted = useRef(false);
  const documentRestoreStarted = useRef(false);
  const loadedDocumentIdRef = useRef<string | null>(null);
  const referenceFileInput = useRef<HTMLInputElement>(null);
  const canUndo = useStore(
    useFlowchartWorkbenchStore.temporal,
    (state) => state.pastStates.length > 0,
  );
  const canRedo = useStore(
    useFlowchartWorkbenchStore.temporal,
    (state) => state.futureStates.length > 0,
  );

  const loadHistory = useCallback(async (offset: number, append: boolean) => {
    setHistoryLoading(true);
    if (!append) {
      setHistoryError(null);
    }
    try {
      const result = await listFlowchartDocuments(offset, HISTORY_PAGE_SIZE);
      if (result.code !== 200 || !result.data) {
        throw new Error(friendlyFailureFrom(result));
      }
      const page = result.data;
      setHistoryRecords((current) =>
        append ? [...current, ...page.records] : page.records,
      );
      setHistoryHasMore(page.hasMore);
    } catch (error) {
      setHistoryError(friendlyFailureFrom(error));
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const refreshHistory = useCallback(
    () => loadHistory(0, false),
    [loadHistory],
  );

  const applyDocument = useCallback(
    (document: FlowchartDocument) => {
      const documentTheme = document.metadata.theme || diagramTheme;
      setDiagramTheme(documentTheme);
      setDiagramData(
        applyDiagramTheme(diagramDataFromDocument(document), documentTheme),
      );
      markDiagramSaved();
      setDirection(document.direction);
      setDocumentVersion(document.metadata.version);
      setMermaidPreview({
        source: document.mermaidSource || null,
        status: document.mermaidCompilation.status,
        error: document.mermaidCompilation.errorMessage,
      });
      setSelectedElement(null);
      saveActiveDocumentId(document.id);
      useFlowchartWorkbenchStore.temporal.getState().clear();
      void refreshHistory();
    },
    [
      markDiagramSaved,
      setDiagramData,
      setDirection,
      setDocumentVersion,
      setMermaidPreview,
      setSelectedElement,
      refreshHistory,
      diagramTheme,
    ],
  );

  const loadDocument = useCallback(
    async (documentId: string) => {
      const result = await getFlowchartDocument(documentId);
      if (result.code !== 200 || !result.data) {
        throw new Error(friendlyFailureFrom(result));
      }
      applyDocument(result.data);
      loadedDocumentIdRef.current = documentId;
      return result.data;
    },
    [applyDocument],
  );

  const onTaskChange = useCallback(
    (nextTask: FlowchartTask) => {
      setTask(nextTask);
      setSubmissionError(null);
    },
    [setTask],
  );
  const { connectionMode } = useTaskMonitor({
    taskId: activeTaskId,
    onTaskChange,
  });

  useEffect(() => {
    const documentId = task?.documentId;
    if (!documentId || loadedDocumentIdRef.current === documentId) {
      return;
    }
    void loadDocument(documentId).catch((error) => {
      setDocumentActionError(friendlyFailureFrom(error));
    });
  }, [loadDocument, task?.documentId]);

  useEffect(() => {
    if (documentRestoreStarted.current) {
      return;
    }
    documentRestoreStarted.current = true;
    const { documentId } = restoreTaskContext();
    if (!documentId) {
      return;
    }
    void loadDocument(documentId)
      .then(() => {
        // 刷新后直接展示已恢复的文档，避免它仅在“编辑”标签中隐式存在。
        setActiveMode('edit');
      })
      .catch(() => {
        // 本地残留的过期文档标识不应阻止工作台继续工作。
      });
  }, [loadDocument]);

  useEffect(() => {
    let disposed = false;
    setProviderLoadState('loading');
    void getFlowchartProviders()
      .then((result) => {
        if (disposed) {
          return;
        }
        if (result.code !== 200 || !result.data) {
          setProviderLoadState('failed');
          return;
        }
        setProviders(result.data);
      })
      .catch(() => {
        if (!disposed) {
          setProviderLoadState('failed');
        }
      });
    return () => {
      disposed = true;
    };
  }, [setProviderLoadState, setProviders]);

  useEffect(() => {
    let disposed = false;
    setTemplateLoadState('loading');
    void getFlowchartTemplates()
      .then((result) => {
        if (disposed) {
          return;
        }
        if (result.code !== 200 || !result.data) {
          setTemplateLoadState('failed');
          return;
        }
        setTemplates(result.data);
      })
      .catch(() => {
        if (!disposed) {
          setTemplateLoadState('failed');
        }
      });
    return () => {
      disposed = true;
    };
  }, [setTemplateLoadState, setTemplates]);

  useEffect(() => {
    void refreshHistory();
  }, [refreshHistory]);

  useEffect(() => {
    if (restoreStarted.current || activeTaskId) {
      return;
    }
    restoreStarted.current = true;
    let disposed = false;

    const restoreTask = async () => {
      const stored = restoreTaskContext();
      if (stored.taskId) {
        if (!disposed) {
          setActiveTaskId(stored.taskId);
        }
        return;
      }

      try {
        const sessionId = getOrCreateFlowchartSessionId();
        let result = await listRecoverableFlowchartTasks(sessionId);
        if (result.code === 200 && !(result.data?.length ?? 0)) {
          result = await listRecoverableFlowchartTasks();
        }
        const recoveredTask =
          result.code === 200 ? result.data?.[0] : undefined;
        if (!disposed && recoveredTask) {
          setTask(recoveredTask);
          setActiveTaskId(recoveredTask.taskId);
        }
      } catch {
        // 恢复失败不妨碍用户直接创建新任务。
      }
    };

    void restoreTask();
    return () => {
      disposed = true;
    };
  }, [activeTaskId, setActiveTaskId, setTask]);

  const modelOptions = useMemo(() => {
    const deduplicated = new Map<string, FlowchartProvider>();
    for (const provider of providers) {
      if (!provider.allowManualSelection) {
        continue;
      }
      const existing = deduplicated.get(provider.displayName);
      if (
        !existing ||
        (existing.status !== 'healthy' && provider.status === 'healthy')
      ) {
        deduplicated.set(provider.displayName, provider);
      }
    }
    return [
      { value: AUTO_ROUTE_MODEL, label: '自动路由' },
      ...Array.from(deduplicated.values()).map((provider) => ({
        value: provider.displayName,
        disabled: provider.status !== 'healthy',
        label: `${provider.displayName} (${providerStatusLabel(provider)})`,
      })),
    ];
  }, [providers]);

  const hasAvailableProvider = providers.some(
    (provider) => provider.status === 'healthy',
  );
  const selectedModelAvailable =
    selectedModel === AUTO_ROUTE_MODEL ||
    providers.some(
      (provider) =>
        provider.displayName === selectedModel && provider.status === 'healthy',
    );
  const hasNoAvailableModel =
    providerLoadState === 'ready' && !hasAvailableProvider;
  const showProviderNotice =
    !providerNoticeDismissed &&
    (providerLoadState === 'failed' || hasNoAvailableModel);
  const canGenerate =
    Boolean(prompt.trim()) &&
    !isCreating &&
    !hasNoAvailableModel &&
    selectedModelAvailable;
  const hasRunningTask =
    isCreating ||
    (Boolean(activeTaskId) && (!task || !isTerminalTaskStatus(task.status)));

  useLeaveConfirmation({ hasRunningTask, hasUnsavedChanges });

  const handleGenerate = async () => {
    if (!canGenerate) {
      return;
    }
    setIsCreating(true);
    setSubmissionError(null);
    setDocumentActionError(null);
    try {
      const result = await createFlowchartTask({
        type: 'diagram_generate',
        prompt: prompt.trim(),
        direction: 'AUTO',
        detailLevel,
        diagramTheme,
        thinkingEnabled,
        providerId: null,
        model: selectedModel === AUTO_ROUTE_MODEL ? null : selectedModel,
        sessionId: getOrCreateFlowchartSessionId(),
        idempotencyKey: createIdempotencyKey(),
      });
      if (result.code !== 200 || !result.data) {
        setSubmissionError(friendlyFailureFrom(result));
        return;
      }

      setTask({
        taskId: result.data.taskId,
        type: 'diagram_generate',
        status: result.data.status,
        progress: 5,
        stage: '任务已创建，等待处理',
      });
      setActiveTaskId(result.data.taskId);
    } catch (error) {
      setSubmissionError(friendlyFailureFrom(error));
    } finally {
      setIsCreating(false);
    }
  };

  const handleCancel = async () => {
    if (!task || !CANCELLABLE_TASK_STATUSES.has(task.status)) {
      return;
    }
    setSubmissionError(null);
    try {
      const result = await cancelFlowchartTask(task.taskId);
      if (result.code !== 200 || !result.data) {
        setSubmissionError(friendlyFailureFrom(result));
        return;
      }
      setTask({
        ...task,
        status: result.data.status,
        progress: 0,
        stage: '任务已取消',
        errorCode: 'TASK_CANCELED',
        errorMessage: '任务已取消',
      });
    } catch (error) {
      setSubmissionError(friendlyFailureFrom(error));
    }
  };

  const handleRetry = async () => {
    if (!task || !['failed', 'canceled', 'expired'].includes(task.status)) {
      return;
    }
    if (task.type === 'diagram_export') {
      setActiveMode('export');
      await handleCreateExport();
      return;
    }
    setSubmissionError(null);
    try {
      const result = await retryFlowchartTask(task.taskId);
      if (result.code !== 200 || !result.data) {
        setSubmissionError(friendlyFailureFrom(result));
        return;
      }
      setTask(null);
      setActiveTaskId(result.data.taskId);
    } catch (error) {
      setSubmissionError(friendlyFailureFrom(error));
    }
  };

  const handleTemplateApply = (description: string) => {
    setPrompt(description);
    setSubmissionError(null);
  };

  const clearDeletedDocumentState = useCallback(() => {
    const emptyDiagram = createEmptyDiagramData();
    setDiagramData(emptyDiagram);
    markDiagramSaved();
    setDirection(emptyDiagram.direction);
    setDocumentVersion(null);
    setMermaidPreview({ source: null, status: 'idle' });
    setSelectedElement(null);
    setTask(null);
    setActiveTaskId(null);
    clearActiveDocumentId();
    clearActiveTaskId();
    loadedDocumentIdRef.current = null;
    useFlowchartWorkbenchStore.temporal.getState().clear();
    setActiveMode('generate');
  }, [
    markDiagramSaved,
    setActiveTaskId,
    setDiagramData,
    setDirection,
    setDocumentVersion,
    setMermaidPreview,
    setSelectedElement,
    setTask,
  ]);

  const handleOpenHistoryDocument = useCallback(
    (record: FlowchartDocumentHistoryItem) => {
      const openDocument = () => {
        setDocumentActionError(null);
        void loadDocument(record.id)
          .then(() => {
            clearActiveTaskId();
            setActiveTaskId(null);
            setTask(null);
            setActiveMode('edit');
          })
          .catch((error) => {
            setDocumentActionError(friendlyFailureFrom(error));
          });
      };
      if (hasUnsavedChanges) {
        Modal.confirm({
          title: '放弃未保存的修改？',
          content: '打开历史流程图会放弃当前画布中的未保存修改。',
          okText: '放弃并打开',
          cancelText: '取消',
          onOk: openDocument,
        });
        return;
      }
      openDocument();
    },
    [hasUnsavedChanges, loadDocument, setActiveTaskId, setTask],
  );

  const handleDeleteHistoryDocument = useCallback(
    async (documentId: string) => {
      setDeletingDocumentId(documentId);
      setDocumentActionError(null);
      try {
        const result = await deleteFlowchartDocument(documentId);
        if (result.code !== 200 || !result.data) {
          throw new Error(friendlyFailureFrom(result));
        }
        setHistoryRecords((current) =>
          current.filter((record) => record.id !== documentId),
        );
        if (diagramData.id === documentId) {
          clearDeletedDocumentState();
        }
        message.success('流程图已永久删除');
        await refreshHistory();
      } catch (error) {
        const errorMessage = friendlyFailureFrom(error);
        setDocumentActionError(errorMessage);
        message.error(errorMessage);
      } finally {
        setDeletingDocumentId(null);
      }
    },
    [clearDeletedDocumentState, diagramData.id, refreshHistory],
  );

  const handleSaveDocument = async () => {
    const documentId = diagramData.id;
    if (!documentId || documentVersion === null) {
      message.warning('请先完成流程图生成后再保存编辑结果');
      return;
    }
    if (!hasUnsavedChanges) {
      message.info('当前没有需要保存的编辑');
      return;
    }

    setIsSaving(true);
    setDocumentActionError(null);
    try {
      const result = await saveFlowchartDocument(documentId, {
        version: documentVersion,
        title: diagramData.title,
        direction: diagramData.direction,
        nodes: diagramData.nodes,
        edges: diagramData.edges,
      });
      if (result.code === 409 && result.data?.latestDocument) {
        applyDocument(result.data.latestDocument);
        message.warning('文档已被更新，已加载最新版本');
        return;
      }
      if (result.code !== 200 || !result.data) {
        setDocumentActionError(friendlyFailureFrom(result));
        return;
      }

      markDiagramSaved();
      setDocumentVersion(result.data.version);
      setMermaidPreview({
        source: result.data.mermaidSource || mermaidSource,
        status: result.data.mermaidCompilation.status,
        error: result.data.mermaidCompilation.errorMessage,
      });
      message.success('流程图已保存，正在编译 Mermaid');
      void refreshHistory();
    } catch (error) {
      setDocumentActionError(friendlyFailureFrom(error));
    } finally {
      setIsSaving(false);
    }
  };

  const handleCreateExport = async () => {
    const documentId = diagramData.id;
    if (!documentId || documentVersion === null) {
      setExportActionError('请先完成流程图生成后再导出');
      return;
    }
    if (hasUnsavedChanges) {
      setExportActionError('请先保存当前编辑，再导出最新版本');
      return;
    }
    setIsExporting(true);
    setExportActionError(null);
    try {
      const result = await createFlowchartDocumentExport(
        documentId,
        exportFormat,
        exportBackground,
      );
      if (result.code !== 200 || !result.data) {
        setExportActionError(friendlyFailureFrom(result));
        return;
      }
      setTask({
        taskId: result.data.taskId,
        type: 'diagram_export',
        status: result.data.status,
        progress: result.data.status === 'success' ? 100 : 5,
        stage:
          result.data.status === 'success' ? '导出文件已生成' : '等待导出渲染',
        documentId,
      });
      setActiveTaskId(result.data.taskId);
    } catch (error) {
      setExportActionError(friendlyFailureFrom(error));
    } finally {
      setIsExporting(false);
    }
  };

  const handleDownloadExport = async () => {
    const downloadUrl = task?.downloadUrl;
    const fileId = downloadUrl?.match(/[?&]fileId=([^&]+)/)?.[1];
    if (!fileId) {
      setExportActionError('导出文件尚未准备好，请稍后刷新任务状态');
      return;
    }
    try {
      const result = await downloadFlowchartFile(fileId);
      const objectUrl = URL.createObjectURL(result.blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = result.filename;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
    } catch (error) {
      setExportActionError(friendlyFailureFrom(error));
    }
  };

  const handleUndo = useCallback(() => {
    useFlowchartWorkbenchStore.temporal.getState().undo();
    setSelectedElement(null);
  }, [setSelectedElement]);

  const handleRedo = useCallback(() => {
    useFlowchartWorkbenchStore.temporal.getState().redo();
    setSelectedElement(null);
  }, [setSelectedElement]);

  const handleDeleteSelectedElement = useCallback(() => {
    if (!selectedElement) {
      return;
    }
    setDiagramData((current) => {
      if (selectedElement.type === 'node') {
        return {
          ...current,
          nodes: current.nodes.filter((node) => node.id !== selectedElement.id),
          edges: current.edges.filter(
            (edge) =>
              edge.source !== selectedElement.id &&
              edge.target !== selectedElement.id,
          ),
        };
      }
      return {
        ...current,
        edges: current.edges.filter((edge) => edge.id !== selectedElement.id),
      };
    });
    setSelectedElement(null);
  }, [selectedElement, setDiagramData, setSelectedElement]);

  const handleDuplicateNode = useCallback(
    (nodeId: string) => {
      let duplicatedId: string | null = null;
      setDiagramData((current) => {
        const source = current.nodes.find((node) => node.id === nodeId);
        if (!source || current.nodes.length >= 50) {
          return current;
        }
        duplicatedId = createUniqueNodeId(current.nodes);
        const duplicate: DiagramNode = {
          ...source,
          id: duplicatedId,
          label: `${source.label} 副本`.slice(0, 120),
          position: {
            x: source.position.x + 40,
            y: source.position.y + 40,
          },
          ...(source.style ? { style: { ...source.style } } : {}),
        };
        return { ...current, nodes: [...current.nodes, duplicate] };
      });
      if (duplicatedId) {
        setSelectedElement({ type: 'node', id: duplicatedId });
      }
    },
    [setDiagramData, setSelectedElement],
  );

  const handleResetDiagram = useCallback(() => {
    resetDiagram();
    setSelectedElement(null);
  }, [resetDiagram, setSelectedElement]);

  useEffect(() => {
    const documentId = diagramData.id;
    if (
      !documentId ||
      documentVersion === null ||
      mermaidStatus !== 'compiling'
    ) {
      return undefined;
    }

    let disposed = false;
    let timer: number | undefined;
    const refreshCompilation = async () => {
      try {
        const result = await getFlowchartDocument(documentId);
        const document = result.code === 200 ? result.data : null;
        if (
          disposed ||
          !document ||
          document.metadata.version !== documentVersion
        ) {
          return;
        }
        setMermaidPreview({
          source: document.mermaidSource || null,
          status: document.mermaidCompilation.status,
          error: document.mermaidCompilation.errorMessage,
        });
        if (document.mermaidCompilation.status === 'compiling') {
          timer = window.setTimeout(() => {
            void refreshCompilation();
          }, 1_000);
        }
      } catch {
        if (!disposed) {
          timer = window.setTimeout(() => {
            void refreshCompilation();
          }, 1_000);
        }
      }
    };
    void refreshCompilation();
    return () => {
      disposed = true;
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
    };
  }, [diagramData.id, documentVersion, mermaidStatus, setMermaidPreview]);

  const presentation = task
    ? (task.type === 'diagram_export'
        ? EXPORT_TASK_PRESENTATIONS
        : TASK_PRESENTATIONS)[task.status]
    : null;
  const currentTaskMessage = task
    ? task.status === 'failed'
      ? friendlyTaskMessage(task.errorCode, task.errorMessage)
      : task.stage || presentation?.description
    : null;
  const directionLabel =
    diagramData.id
      ? direction === 'TB'
        ? '自上而下'
        : '从左到右'
      : '由 AI 自主决定';
  const projectTitle = diagramData.title || '未命名流程图';

  return (
    <main className={styles.workbench} data-task-connection={connectionMode}>
      <aside className={styles.sidebar} aria-label="项目导航">
        <div className={styles.brand}>
          <span className={styles.logoMark} aria-hidden="true"><ApartmentOutlined /></span>
          <div><strong>FlowPilot AI</strong><span>智能流程图工作台</span></div>
        </div>
        <Button className={styles.newProjectButton} type="primary" icon={<PlusOutlined />} onClick={handleResetDiagram}>新建流程图</Button>
        <button className={styles.uploadBox} type="button" onClick={() => referenceFileInput.current?.click()}>
          <UploadOutlined /><strong>上传参考文件</strong><span>支持 PDF、Word、图片<br />AI 将自动提取流程信息</span>
        </button>
        <input ref={referenceFileInput} className={styles.hiddenInput} type="file" accept=".pdf,.doc,.docx,image/*" onChange={(event) => { const file = event.target.files?.[0]; if (file) message.success(`已选择参考文件：${file.name}`); }} />
        <div className={styles.sidebarSectionTitle}><ClockCircleOutlined /> 最近项目 {historyLoading ? <Spin size="small" /> : null}</div>
        <div className={styles.historyList}>
          {historyError ? <Typography.Text type="secondary">最近项目暂时无法加载</Typography.Text> : null}
          {historyRecords.map((record) => (
            <div key={record.id} className={`${styles.historyItem} ${diagramData.id === record.id ? styles.historyItemActive : ''}`}>
              <button className={styles.historyOpenButton} type="button" onClick={() => handleOpenHistoryDocument(record)}><span className={styles.historyIcon}><ApartmentOutlined /></span><span><strong>{record.title}</strong><small>{record.updatedAt}</small></span></button>
              <Popconfirm title="永久删除此流程图？" okText="永久删除" cancelText="取消" okButtonProps={{ danger: true }} onConfirm={() => handleDeleteHistoryDocument(record.id)}><Button aria-label={`删除 ${record.title}`} danger icon={<DeleteOutlined />} loading={deletingDocumentId === record.id} size="small" type="text" /></Popconfirm>
            </div>
          ))}
          {!historyRecords.length && !historyLoading ? <Typography.Text type="secondary">暂无最近项目</Typography.Text> : null}
        </div>
        {historyHasMore ? <Button type="link" size="small" onClick={() => void loadHistory(historyRecords.length, true)}>加载更多</Button> : null}
        <div className={styles.sidebarFooter}><span className={styles.statusDot} /><span>AI 服务运行正常</span><Typography.Text type="secondary">{hasNoAvailableModel ? '暂无可用模型' : '模型已连接'}</Typography.Text></div>
      </aside>

      <section className={styles.canvasPanel} aria-label="流程图画布">
        <header className={styles.canvasHeader}>
          <div className={styles.projectHeader}><span className={styles.projectIcon}><ApartmentOutlined /></span><div><strong>{projectTitle}</strong><span><i /> {hasUnsavedChanges ? '有未保存修改' : '已自动保存'}</span></div></div>
          <div className={styles.headerActions}><Button size="small" icon={<ReloadOutlined />} onClick={handleResetDiagram}>重置画布</Button><Button size="small" icon={<SaveOutlined />} disabled={!hasUnsavedChanges} loading={isSaving} onClick={() => void handleSaveDocument()}>保存</Button></div>
        </header>
        <div className={styles.canvasModeBar}><Segmented value={activeMode} options={[{ label: '生成', value: 'generate', icon: <PlayCircleOutlined /> }, { label: '编辑', value: 'edit', icon: <EditOutlined /> }, { label: 'Mermaid', value: 'mermaid', icon: <FileTextOutlined /> }, { label: '导出', value: 'export', icon: <ExportOutlined />, disabled: !diagramData.id || documentVersion === null }]} onChange={(value) => setActiveMode(value as 'generate' | 'edit' | 'mermaid' | 'export')} /></div>
        <div className={`${styles.previewContent} ${activeMode === 'edit' ? styles.canvasContent : ''} ${activeMode === 'mermaid' ? styles.mermaidContent : ''}`}>
            {activeMode === 'edit' ? (
              <DiagramCanvas
                diagramData={diagramData}
                selectedElement={selectedElement}
                onChange={setDiagramData}
                onSelectElement={setSelectedElement}
                onReset={handleResetDiagram}
                onUndo={handleUndo}
                onRedo={handleRedo}
                canUndo={canUndo}
                canRedo={canRedo}
                theme={diagramTheme}
              />
            ) : activeMode === 'mermaid' ? (
              <MermaidPanel
                source={mermaidSource}
                status={mermaidStatus}
                error={mermaidError}
              />
            ) : activeMode === 'export' ? (
              <div className={styles.exportPanel}>
                <div className={styles.exportPanelHeader}>
                  <Typography.Title level={4}>导出流程图</Typography.Title>
                  <Typography.Text type="secondary">导出使用当前已保存的文档版本，不影响画布编辑。</Typography.Text>
                </div>
                <div className={styles.exportField}>
                  <Typography.Text strong>文件格式</Typography.Text>
                  <div className={styles.exportOptions} role="radiogroup" aria-label="文件格式">
                    {([
                      ['SVG', 'SVG'],
                      ['PNG', 'PNG'],
                      ['Mermaid', 'MERMAID'],
                      ['JSON', 'JSON'],
                    ] as const).map(([label, value]) => (
                      <button
                        key={value}
                        type="button"
                        role="radio"
                        aria-checked={exportFormat === value}
                        className={`${styles.exportOption} ${exportFormat === value ? styles.exportOptionSelected : ''}`}
                        onClick={() => setExportFormat(value as FlowchartExportFormat)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                {(exportFormat === 'SVG' || exportFormat === 'PNG') && (
                  <div className={styles.exportField}>
                    <Typography.Text strong>背景</Typography.Text>
                    <div className={`${styles.exportOptions} ${styles.backgroundOptions}`} role="radiogroup" aria-label="背景">
                      {([
                        ['透明', 'transparent'],
                        ['白色', 'white'],
                      ] as const).map(([label, value]) => (
                        <button
                          key={value}
                          type="button"
                          role="radio"
                          aria-checked={exportBackground === value}
                          className={`${styles.exportOption} ${exportBackground === value ? styles.exportOptionSelected : ''}`}
                          onClick={() => setExportBackground(value)}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                <Button className={styles.exportSubmit}
                  type="primary"
                  icon={<ExportOutlined />}
                  loading={isExporting}
                  onClick={() => void handleCreateExport()}
                >
                  创建导出
                </Button>
                {exportActionError ? (
                  <Alert type="error" showIcon message={exportActionError} />
                ) : null}
                {task?.type === 'diagram_export' &&
                task.status === 'success' ? (
                  <Button
                    icon={<DownloadOutlined />}
                    onClick={() => void handleDownloadExport()}
                  >
                    下载文件
                  </Button>
                ) : null}
              </div>
            ) : isCreating ? (
              <div className={styles.processingState}>
                <Spin indicator={<LoadingOutlined spin />} size="large" />
                <Typography.Text type="secondary">正在创建任务</Typography.Text>
              </div>
            ) : !task ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  <Typography.Text type="secondary">
                    输入描述后开始生成流程图
                  </Typography.Text>
                }
              />
            ) : task.status === 'success' ? (
              <div className={styles.generatedPreview}>
                <MermaidDiagram
                  source={mermaidSource}
                  status={mermaidStatus}
                  error={mermaidError}
                  theme={diagramTheme}
                />
                <div className={styles.generatedPreviewActions}>
                  <CheckCircleFilled aria-hidden="true" />
                  <Typography.Text type="secondary">
                    AI 已生成流程图，可继续调整节点和连线。
                  </Typography.Text>
                  <Button
                    icon={<EditOutlined />}
                    onClick={() => setActiveMode('edit')}
                  >
                    打开编辑器
                  </Button>
                </div>
              </div>
            ) : task.status === 'failed' ? (
              <div className={styles.failureState}>
                <Typography.Title level={4}>生成失败</Typography.Title>
                <Typography.Paragraph>
                  {currentTaskMessage}
                </Typography.Paragraph>
              </div>
            ) : task.status === 'canceled' || task.status === 'expired' ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  <Typography.Text type="secondary">
                    {presentation?.label}
                  </Typography.Text>
                }
              />
            ) : (
              <div className={styles.processingState}>
                <Spin size="large" />
                <Typography.Title level={4}>
                  {presentation?.label}
                </Typography.Title>
                <Typography.Text type="secondary">
                  {currentTaskMessage}
                </Typography.Text>
              </div>
            )}
          </div>
        </section>

        <aside className={styles.assistantPanel} aria-label="AI 流程图助手">
          <header className={styles.assistantHeader}>
            <span>FLOWCHART GENERATOR</span>
            <h1>AI 流程图助手</h1>
            <p>输入一句描述，自动整理逻辑、节点与流程关系。</p>
          </header>
          <div className={styles.assistantBody}>
            {showProviderNotice ? <Alert className={styles.providerNotice} type="warning" showIcon closable message="当前默认供应商响应异常，正在尝试降级/路由" onClose={dismissProviderNotice} /> : null}
            {activeMode === 'edit' ? <NodePropertyPanel diagramData={diagramData} selectedElement={selectedElement} onChange={setDiagramData} onSelectElement={setSelectedElement} onDeleteSelected={handleDeleteSelectedElement} onDuplicateNode={handleDuplicateNode} /> : activeMode === 'export' ? <div className={styles.exportSummary}><Typography.Text strong>导出任务</Typography.Text><dl className={styles.detailList}><div><dt>文件格式</dt><dd>{exportFormat}</dd></div><div><dt>任务状态</dt><dd>{presentation?.label || '等待创建'}</dd></div><div><dt>文档版本</dt><dd>{documentVersion ?? '-'}</dd></div></dl></div> : <>
              <section className={styles.promptCard}>
                <h2>开始创建你的流程图</h2>
                <p>越清晰地描述场景、角色与步骤，生成结果越准确。</p>
                <div className={styles.assistantTabs}><button className={styles.assistantTabActive} type="button">文字生成</button><button type="button" onClick={() => referenceFileInput.current?.click()}>参考文件</button></div>
                <Input.TextArea id="flowchart-prompt" value={prompt} maxLength={4000} autoSize={{ minRows: 5, maxRows: 8 }} placeholder="例如：生成一个电商订单从用户下单、支付、仓库发货到售后评价的完整流程图" onChange={(event) => setPrompt(event.target.value)} />
                <div className={styles.formGrid}>
                  <Select value={direction} options={[{ value: 'LR', label: '横向布局' }, { value: 'TB', label: '纵向布局' }]} onChange={(value) => setDirection(value as 'LR' | 'TB')} />
                  <Select value={detailLevel} options={[{ value: 'concise', label: '简要' }, { value: 'standard', label: '标准' }, { value: 'detailed', label: '详细' }]} onChange={(value) => setDetailLevel(value as 'concise' | 'standard' | 'detailed')} />
                  <Select value={selectedModel} loading={providerLoadState === 'loading'} disabled={hasNoAvailableModel} options={modelOptions} onChange={setSelectedModel} />
                  <Select value={diagramTheme} options={[{ value: 'blue', label: '商务蓝' }, { value: 'purple', label: '科技紫' }, { value: 'green', label: '清新绿' }]} onChange={(value) => { const nextTheme = value as DiagramTheme; setDiagramTheme(nextTheme); if (diagramData.id || diagramData.nodes.length) { setDiagramData((current) => applyDiagramTheme(current, nextTheme)); } }} />
                </div>
                <div className={styles.thinkingOption}>
                  <div className={styles.thinkingCopy}>
                    <span className={styles.thinkingTitle}>深度思考</span>
                    <Typography.Text type="secondary">
                      默认关闭，开启后模型会进行更深入分析
                    </Typography.Text>
                  </div>
                  <Switch
                    checked={thinkingEnabled}
                    aria-label="深度思考"
                    onChange={setThinkingEnabled}
                  />
                </div>
                <Button className={styles.generateButton} type="primary" icon={<SendOutlined />} loading={isCreating} disabled={!canGenerate} onClick={() => void handleGenerate()}>生成流程图</Button>
              </section>
              <section className={styles.templateSection}><div className={styles.templateHeader}><strong>常用流程模板</strong><span>点击快速生成</span></div>{templateLoadState === 'loading' ? <Spin size="small" /> : templateLoadState === 'failed' ? <Typography.Text type="secondary">内置模板暂不可用</Typography.Text> : <div className={styles.templateList}>{templates.map((template) => <button key={template.id} className={styles.templateItem} type="button" onClick={() => handleTemplateApply(template.description)}><strong>{template.name}</strong><span>{template.description}</span></button>)}</div>}</section>
            </>}
            {activeMode !== 'edit' && activeMode !== 'export' ? <div className={styles.assistantStatus}><Badge status={isCreating ? 'processing' : presentation?.badge || 'default'} text={isCreating ? '正在创建任务' : presentation?.label || '等待生成'} /><Typography.Text type="secondary">{submissionError || documentActionError || currentTaskMessage || getConnectionLabel(connectionMode, Boolean(task))}</Typography.Text>{task && CANCELLABLE_TASK_STATUSES.has(task.status) ? <Button size="small" icon={<StopOutlined />} onClick={() => void handleCancel()}>取消</Button> : null}{task && ['failed', 'canceled', 'expired'].includes(task.status) ? <Button size="small" icon={<ReloadOutlined />} onClick={() => void handleRetry()}>重试</Button> : null}</div> : null}
          </div>
        </aside>
    </main>
  );
};

export default FlowchartWorkbench;
