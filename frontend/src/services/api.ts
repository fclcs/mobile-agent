import axios, { AxiosInstance, AxiosError } from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

// 创建axios实例
const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
  maxRedirects: 5,
});

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    // 可以在这里添加token等认证信息
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器
api.interceptors.response.use(
  (response) => response.data,
  (error: AxiosError) => {
    if (error.response) {
      // 服务器返回错误状态码
      console.error('API Error:', error.response.status, error.response.data);
    } else if (error.request) {
      // 请求发出但没有收到响应
      console.error('Network Error:', error.request);
    } else {
      // 请求配置出错
      console.error('Request Error:', error.message);
    }
    return Promise.reject(error);
  }
);

// 设备相关API
export const deviceApi = {
  getDevices: () => api.get('/api/v1/devices/'),
  getDevice: (deviceId: string) => api.get(`/api/v1/devices/${deviceId}`),
  registerDevice: (data: {
    device_id: string;
    name?: string;
    remark?: string;
    group_name?: string;
    platform?: string;
  }) => api.post('/api/v1/devices/', data),
  updateDevice: (deviceId: string, data: {
    name?: string;
    remark?: string;
    group_name?: string;
    enabled?: boolean;
  }) => api.put(`/api/v1/devices/${encodeURIComponent(deviceId)}`, data),
  deleteDevice: (deviceId: string) =>
    api.delete(`/api/v1/devices/${encodeURIComponent(deviceId)}`),
  connectDevice: (deviceId: string) => api.post(`/api/v1/devices/${deviceId}/connect`),
  disconnectDevice: (deviceId: string) => api.post(`/api/v1/devices/${deviceId}/disconnect`),
  getScreenshot: (deviceId: string) => api.get(`/api/v1/devices/${deviceId}/screenshot`),
  launchApp: (deviceId: string, packageName: string) =>
    api.post(`/api/v1/devices/${deviceId}/launch`, { package_name: packageName }),
  connectTcpIp: (ipPort: string) => api.post('/api/v1/devices/tcpip/connect', { ip_port: ipPort }),
  disconnectTcpIp: (ipPort: string) => api.post(`/api/v1/devices/tcpip/disconnect/${ipPort}`),
  enableWireless: (deviceId: string, port: number = 5555) =>
    api.post(`/api/v1/devices/${deviceId}/wireless`, { port }),
  getDeviceIp: (deviceId: string) => api.get(`/api/v1/devices/${deviceId}/ip`),
};

// 任务相关API
export const taskApi = {
  getTasks: (params?: { skip?: number; limit?: number; status?: string }) =>
    api.get('/api/v1/tasks/', { params }),
  getTask: (taskId: string) => api.get(`/api/v1/tasks/${taskId}`),
  createTask: (data: {
    name: string;
    description: string;
    script_id: string;
    device_id: string;
    apk_id?: string;
    model_config_id?: string;
  }) => api.post('/api/v1/tasks/', data),
  executeTask: (taskId: string) => api.post(`/api/v1/tasks/${taskId}/execute`),
  stopTask: (taskId: string) => api.post(`/api/v1/tasks/${taskId}/stop`),
  deleteTask: (taskId: string) => api.delete(`/api/v1/tasks/${taskId}`),
  getTaskLogs: (taskId: string, limit?: number) => api.get(`/api/v1/tasks/${taskId}/logs`, { params: { limit } }),
  batchDeleteTasks: (taskIds: string[]) =>
    api.delete('/api/v1/tasks/batch', { data: { task_ids: taskIds } }),
  executeNaturalLanguageTask: (data: {
    task_description: string;
    device_id?: string;
    platform?: string;
    max_steps?: number;
    mode?: string;
    save_task?: boolean;
  }) => api.post('/api/v1/tasks/natural-language', data),
};

// 脚本相关API
export const scriptApi = {
  getScripts: (params?: { skip?: number; limit?: number; script_type?: string }) =>
    api.get('/api/v1/scripts/', { params }),
  getScript: (scriptId: string) => api.get(`/api/v1/scripts/${scriptId}`),
  createScript: (data: {
    name: string;
    description: string;
    platform: string;
    content?: string;
  }) => api.post('/api/v1/scripts/', data),
  uploadScript: (formData: FormData) =>
    api.post('/api/v1/scripts/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  updateScript: (scriptId: string, data: { content?: string; name?: string }) =>
    api.put(`/api/v1/scripts/${scriptId}`, data),
  generateScript: (data: {
    task_description: string;
    platform: string;
    device_id?: string;
  }) => api.post('/api/v1/scripts/generate', data),
  executeScript: (scriptId: string, deviceId?: string, modelConfigId?: string) =>
    api.post(`/api/v1/scripts/${scriptId}/execute`, {
      device_id: deviceId,
      model_config_id: modelConfigId,
    }),
  getScriptVersions: (scriptId: string) => api.get(`/api/v1/scripts/${scriptId}/versions`),
  deleteScript: (scriptId: string) => api.delete(`/api/v1/scripts/${scriptId}`),
};

// 流程编排与截图记录 API
export interface WorkflowScript {
  script_id: string;
  name: string;
  platform: string;
}

export interface WorkflowDefinition {
  workflow_id: string;
  name: string;
  description: string;
  script_ids: string[];
  continue_on_error: boolean;
  step_timeout: number;
  scripts: WorkflowScript[];
  created_at: string;
  updated_at?: string;
}

export interface WorkflowRunStep {
  step_id: string;
  run_id: string;
  step_order: number;
  script_id: string;
  script_name: string;
  status: 'pending' | 'executing' | 'completed' | 'failed' | 'skipped' | 'cancelled';
  exit_code?: number;
  output: string;
  error?: string;
  screenshot_path?: string;
  screenshot_url?: string;
  captured_at?: string;
  started_at?: string;
  completed_at?: string;
}

export interface WorkflowRun {
  run_id: string;
  workflow_id: string;
  workflow_name: string;
  device_id: string;
  device_name?: string;
  batch_id?: string;
  status: 'pending' | 'executing' | 'completed' | 'partial' | 'failed' | 'cancelled';
  current_step: number;
  total_steps: number;
  error?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  steps: WorkflowRunStep[];
}

export interface WorkflowScreenshot {
  step_id: string;
  run_id: string;
  workflow_id: string;
  workflow_name: string;
  step_order: number;
  script_id: string;
  script_name: string;
  status: string;
  device_id: string;
  captured_at: string;
  screenshot_path: string;
  screenshot_url: string;
}

export const workflowApi = {
  getWorkflows: () => api.get('/api/v1/workflows/'),
  getWorkflow: (workflowId: string) => api.get(`/api/v1/workflows/${workflowId}`),
  createWorkflow: (data: {
    name: string;
    description: string;
    script_ids: string[];
    continue_on_error?: boolean;
    step_timeout?: number;
  }) => api.post('/api/v1/workflows/', data),
  updateWorkflow: (
    workflowId: string,
    data: {
      name?: string;
      description?: string;
      script_ids?: string[];
      continue_on_error?: boolean;
      step_timeout?: number;
    },
  ) => api.put(`/api/v1/workflows/${workflowId}`, data),
  deleteWorkflow: (workflowId: string) => api.delete(`/api/v1/workflows/${workflowId}`),
  executeWorkflow: (workflowId: string, deviceIds: string[]) =>
    api.post(`/api/v1/workflows/${workflowId}/execute`, { device_ids: deviceIds }),
  getRuns: (workflowId?: string) =>
    api.get('/api/v1/workflows/runs', { params: { workflow_id: workflowId } }),
  getRun: (runId: string) => api.get(`/api/v1/workflows/runs/${runId}`),
  cancelRun: (runId: string) => api.post(`/api/v1/workflows/runs/${runId}/cancel`),
  deleteRun: (runId: string) => api.delete(`/api/v1/workflows/runs/${runId}`),
  batchDeleteRuns: (runIds: string[]) =>
    api.post('/api/v1/workflows/runs/batch-delete', { run_ids: runIds }),
  getScreenshots: (workflowId?: string) =>
    api.get('/api/v1/workflows/screenshots', { params: { workflow_id: workflowId } }),
  getScreenshotUrl: (stepId: string) =>
    `${API_BASE_URL}/api/v1/workflows/screenshots/${encodeURIComponent(stepId)}/image`,
};

// 报告相关API
export const reportApi = {
  getReports: (params?: { task_id?: string; status?: string; skip?: number; limit?: number }) =>
    api.get('/api/v1/reports/', { params }),
  getReport: (reportId: string) => api.get(`/api/v1/reports/${reportId}`),
  generateReport: (reportId: string) => api.post(`/api/v1/reports/${reportId}/generate`),
  downloadReport: (reportId: string, format: string = 'html') =>
    api.get(`/api/v1/reports/${reportId}/download`, { params: { format }, responseType: 'blob' }),
  getReportPreview: (reportId: string) => api.get(`/api/v1/reports/${reportId}/preview`),
  deleteReport: (reportId: string) => api.delete(`/api/v1/reports/${reportId}`),
  batchDeleteReports: (reportIds: string[]) =>
    api.delete('/api/v1/reports/batch', { data: { report_ids: reportIds } }),
};

// APK相关API
export const apkApi = {
  getApks: () => api.get('/api/v1/apks/'),
  getApk: (apkId: string) => api.get(`/api/v1/apks/${apkId}`),
  uploadApk: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/api/v1/apks/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  deleteApk: (apkId: string) => api.delete(`/api/v1/apks/${apkId}`),
  batchDeleteApks: (apkIds: string[]) =>
    api.delete('/api/v1/apks/batch', { data: { apk_ids: apkIds } }),
  installApk: (deviceId: string, apkId: string) =>
    api.post('/api/v1/apks/install', { device_id: deviceId, apk_id: apkId }),
};

// 项目相关API
export const projectApi = {
  getProjects: (params?: { skip?: number; limit?: number }) =>
    api.get('/api/v1/projects/', { params }),
  getProject: (projectId: string) => api.get(`/api/v1/projects/${projectId}`),
  createProject: (data: {
    name: string;
    description: string;
    platform?: string;
  }) => api.post('/api/v1/projects/', data),
  updateProject: (projectId: string, data: {
    name?: string;
    description?: string;
    platform?: string;
  }) => api.put(`/api/v1/projects/${projectId}`, data),
  deleteProject: (projectId: string) => api.delete(`/api/v1/projects/${projectId}`),
};

// 模型配置相关API
export const modelConfigApi = {
  getConfigs: () => api.get('/api/v1/model_configs/'),
  getConfig: (id: string) => api.get(`/api/v1/model_configs/${id}`),
  createConfig: (data: any) => api.post('/api/v1/model_configs/', data),
  updateConfig: (id: string, data: any) => api.put(`/api/v1/model_configs/${id}`, data),
  deleteConfig: (id: string) => api.delete(`/api/v1/model_configs/${id}`),
  getDefaultConfig: () => api.get('/api/v1/model_configs/default'),
  testConfig: (data: any) => api.post('/api/v1/model_configs/test', data),
  testSavedConfig: (id: string) => api.post(`/api/v1/model_configs/${id}/test`),
};

// 脚本视觉识别模型（独立于手机操作模型）
export interface VisionModelConfig {
  provider: string;
  base_url: string;
  api_key: string;
  model_name: string;
  disable_thinking: boolean;
  api_key_configured: boolean;
  configured: boolean;
  updated_at?: string | null;
}

export const visionModelApi = {
  get: () => api.get('/api/v1/vision_model_config/') as Promise<VisionModelConfig>,
  update: (data: Record<string, any>) =>
    api.put('/api/v1/vision_model_config/', data) as Promise<VisionModelConfig>,
  test: (data?: Record<string, any>) =>
    api.post('/api/v1/vision_model_config/test', data ?? {}) as Promise<{
      success: boolean;
      message: string;
      response_time_ms?: number;
    }>,
};

// 设置相关API
export const settingsApi = {
  getSettings: () => api.get('/api/v1/settings/'),
  updateSettings: (data: Record<string, any>) => api.put('/api/v1/settings/', data),
};

// 救援服务（oag-rescue）相关API
export interface RescueStep {
  seq: number;
  phase: string;
  detail: string;
  ok: number | null;
  screenshot?: string | null;
  created_at: string;
}

export interface RescueRun {
  rescue_id: string;
  run_id: string;
  step_id: string;
  device_id: string;
  script_name: string;
  app: string;
  package: string;
  goal: string;
  expected: string;
  status: string;
  handler: string;
  resolved: boolean;
  vision_calls: number;
  tool_calls: number;
  evidence: string;
  state_patch: Record<string, any>;
  error: string;
  created_at: string;
  finished_at: string | null;
  steps?: RescueStep[];
}

// 响应拦截器把 AxiosResponse 解包成 data，但类型声明仍按 AxiosResponse，这里统一收口。
const rescueData = <T,>(promise: any): Promise<T> => promise as Promise<T>;

export const rescueApi = {
  getHealth: () => rescueData<any>(api.get('/api/v1/rescue/health')),
  getStats: () => rescueData<any>(api.get('/api/v1/rescue/stats')),
  getRuns: (params?: { run_id?: string; step_id?: string; limit?: number }) =>
    rescueData<{ items: RescueRun[] }>(api.get('/api/v1/rescue/runs', { params })),
  getRun: (rescueId: string) =>
    rescueData<RescueRun>(api.get(`/api/v1/rescue/runs/${rescueId}`)),
  getSettings: () => rescueData<any>(api.get('/api/v1/rescue/settings')),
  updateSettings: (data: Record<string, any>) =>
    rescueData<any>(api.put('/api/v1/rescue/settings', data)),
  testSettings: (data: Record<string, any>) =>
    rescueData<{ success: boolean; message: string }>(api.post('/api/v1/rescue/settings/test', data)),
  getSkills: () =>
    rescueData<{ active: any[]; drafts: any[] }>(api.get('/api/v1/rescue/skills')),
  promoteSkill: (name: string) =>
    rescueData<any>(api.post(`/api/v1/rescue/skills/${name}/promote`)),
  screenshotUrl: (path: string) => `/api/v1/rescue/screenshots/${path}`,
};

// 日志相关API
export const logApi = {
  getLogs: (params?: {
    level?: string;
    category?: string;
    device_id?: string;
    script_id?: string;
    task_id?: string;
    search?: string;
    start_time?: string;
    end_time?: string;
    skip?: number;
    limit?: number;
  }) => api.get('/api/v1/logs/', { params }),
  getSummary: () => api.get('/api/v1/logs/summary'),
  clearLogs: () => api.delete('/api/v1/logs/'),
};

export default api;
