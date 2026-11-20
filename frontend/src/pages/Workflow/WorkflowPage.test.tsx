import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WorkflowPage } from './WorkflowPage';
import { deviceApi, scriptApi, workflowApi } from '../../services/api';
import type { WorkflowDefinition, WorkflowRun } from '../../services/api';

jest.mock('../../services/api', () => ({
  deviceApi: { getDevices: jest.fn() },
  scriptApi: { getScripts: jest.fn() },
  workflowApi: {
    getWorkflows: jest.fn(),
    getWorkflow: jest.fn(),
    createWorkflow: jest.fn(),
    updateWorkflow: jest.fn(),
    deleteWorkflow: jest.fn(),
    executeWorkflow: jest.fn(),
    getRuns: jest.fn(),
    getRun: jest.fn(),
    cancelRun: jest.fn(),
    deleteRun: jest.fn(),
    batchDeleteRuns: jest.fn(),
    getScreenshotUrl: jest.fn(),
  },
}));

type MockedApi = {
  getWorkflows: jest.Mock;
  getRuns: jest.Mock;
  getRun: jest.Mock;
  executeWorkflow: jest.Mock;
  cancelRun: jest.Mock;
  deleteRun: jest.Mock;
  batchDeleteRuns: jest.Mock;
  createWorkflow: jest.Mock;
};

const mockedWorkflowApi = workflowApi as unknown as MockedApi;

const workflow: WorkflowDefinition = {
  workflow_id: 'wf-1',
  name: '测试流程',
  description: '用于测试的流程',
  script_ids: ['script-1'],
  continue_on_error: false,
  step_timeout: 0,
  scripts: [{ script_id: 'script-1', name: '脚本一', platform: 'android' }],
  created_at: '2026-11-15T10:00:00',
};

function makeRun(overrides: Partial<WorkflowRun>): WorkflowRun {
  return {
    run_id: 'run-1',
    workflow_id: 'wf-1',
    workflow_name: '测试流程',
    device_id: '10.0.0.11:5555',
    device_name: '手机1',
    status: 'completed',
    current_step: 1,
    total_steps: 1,
    created_at: '2026-11-15T10:51:18',
    steps: [],
    ...overrides,
  };
}

function completedRun(runId = 'run-done'): WorkflowRun {
  return makeRun({ run_id: runId, status: 'completed' });
}

function failedRun(runId = 'run-failed'): WorkflowRun {
  return makeRun({ run_id: runId, status: 'failed', error: '脚本退出码 1' });
}

function runningRun(runId = 'run-live'): WorkflowRun {
  return makeRun({ run_id: runId, status: 'executing', total_steps: 2, current_step: 1 });
}

let runs: WorkflowRun[];

async function renderPage() {
  render(<WorkflowPage />);
  await screen.findByText('执行历史');
}

beforeEach(() => {
  jest.clearAllMocks();
  runs = [];
  (scriptApi.getScripts as jest.Mock).mockResolvedValue({ scripts: [] });
  (deviceApi.getDevices as jest.Mock).mockResolvedValue({
    devices: [
      {
        device_id: '10.0.0.11:5555',
        name: '手机1',
        platform: 'android',
        status: 'connected',
      },
    ],
  });
  mockedWorkflowApi.getWorkflows.mockResolvedValue({ workflows: [workflow] });
  mockedWorkflowApi.getRuns.mockImplementation(async (workflowId?: string) => ({
    runs: workflowId ? runs.filter(run => run.workflow_id === workflowId) : runs,
  }));
  mockedWorkflowApi.getRun.mockImplementation(async (runId: string) =>
    runs.find(run => run.run_id === runId) ?? null,
  );
  mockedWorkflowApi.deleteRun.mockImplementation(async (runId: string) => {
    runs = runs.filter(run => run.run_id !== runId);
    return { deleted: 1, run_ids: [runId], screenshot_files: 0 };
  });
  mockedWorkflowApi.batchDeleteRuns.mockImplementation(async (runIds: string[]) => {
    runs = runs.filter(run => !runIds.includes(run.run_id));
    return { deleted: runIds.length, run_ids: runIds, screenshot_files: 0 };
  });
  jest.spyOn(window, 'confirm').mockReturnValue(true);
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe('WorkflowPage 执行历史删除', () => {
  it('勾选已结束记录后单条删除，刷新列表并提示成功', async () => {
    runs = [completedRun(), failedRun()];
    await renderPage();
    await screen.findAllByText(/手机1 ·/);

    fireEvent.click(screen.getAllByTitle('删除该执行记录')[0]);

    await waitFor(() => expect(mockedWorkflowApi.deleteRun).toHaveBeenCalledWith('run-done'));
    expect(window.confirm).toHaveBeenCalled();
    await screen.findByText('执行记录已删除');
    await waitFor(() =>
      expect(mockedWorkflowApi.getRuns).toHaveBeenCalledWith(workflow.workflow_id),
    );
    expect(mockedWorkflowApi.getRuns).toHaveBeenCalledWith();
  });

  it('全选后批量删除，确认文案包含条数', async () => {
    runs = [completedRun(), failedRun()];
    await renderPage();
    await screen.findAllByText(/手机1 ·/);

    fireEvent.click(screen.getByRole('button', { name: '全选（2）' }));
    const checkboxes = screen.getAllByRole('checkbox') as HTMLInputElement[];
    expect(checkboxes.every(box => box.checked)).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: '批量删除（2）' }));

    await waitFor(() =>
      expect(mockedWorkflowApi.batchDeleteRuns).toHaveBeenCalledWith(['run-done', 'run-failed']),
    );
    expect((window.confirm as jest.Mock).mock.calls[0][0]).toContain('2 条');
    await screen.findByText('已删除 2 条执行记录');
    await screen.findByText('暂无执行记录，点击上方“一键执行”开始');
  });

  it('再次点击全选会取消选择，批量删除按钮恢复禁用', async () => {
    runs = [completedRun(), failedRun()];
    await renderPage();
    await screen.findAllByText(/手机1 ·/);

    fireEvent.click(screen.getByRole('button', { name: '全选（2）' }));
    fireEvent.click(screen.getByRole('button', { name: '取消全选' }));

    const checkboxes = screen.getAllByRole('checkbox') as HTMLInputElement[];
    expect(checkboxes.some(box => box.checked)).toBe(false);
    expect(screen.getByRole('button', { name: '批量删除' })).toBeDisabled();
  });

  it('运行中的记录不能勾选，只显示中断按钮', async () => {
    runs = [runningRun()];
    await renderPage();
    await screen.findAllByText(/手机1 ·/);

    const checkbox = screen.getByTitle('运行中的记录不能删除，请先中断') as HTMLInputElement;
    expect(checkbox).toBeDisabled();
    expect(screen.getByRole('button', { name: '中断' })).toBeInTheDocument();
    expect(screen.queryByTitle('删除该执行记录')).toBeNull();
  });

  it('勾选运行中的记录不会进入批量删除（复选框禁用）', async () => {
    const user = userEvent.setup();
    runs = [runningRun()];
    await renderPage();
    await screen.findAllByText(/手机1 ·/);

    await user.click(screen.getByTitle('运行中的记录不能删除，请先中断'));
    expect(screen.getByRole('button', { name: '批量删除' })).toBeDisabled();
  });
});

describe('WorkflowPage 中断流程', () => {
  it('中断成功后刷新记录并提示已中断', async () => {
    runs = [runningRun()];
    mockedWorkflowApi.cancelRun.mockImplementation(async (runId: string) => {
      runs = runs.map(run => (run.run_id === runId ? { ...run, status: 'cancelled' } : run));
      return runs[0];
    });
    await renderPage();
    await screen.findAllByText(/手机1 ·/);

    fireEvent.click(screen.getByRole('button', { name: '中断' }));

    await waitFor(() => expect(mockedWorkflowApi.cancelRun).toHaveBeenCalledWith('run-live'));
    expect((window.confirm as jest.Mock).mock.calls[0][0]).toContain('已中断');
    await screen.findByText('已中断该执行记录，后续步骤已跳过');
    await waitFor(() => expect(screen.getAllByText('已中断').length).toBeGreaterThan(0));
    expect(screen.queryByRole('button', { name: '中断' })).toBeNull();
  });

  it('中断失败时展示后端错误信息，按钮可再次重试', async () => {
    runs = [runningRun()];
    const failure = Object.assign(new Error('Request failed'), {
      response: { data: { detail: '该执行记录已结束，不能中断' } },
    });
    mockedWorkflowApi.cancelRun.mockRejectedValue(failure);
    await renderPage();
    await screen.findAllByText(/手机1 ·/);

    fireEvent.click(screen.getByRole('button', { name: '中断' }));

    await screen.findByText('该执行记录已结束，不能中断');
    await waitFor(() => expect(screen.getByRole('button', { name: '中断' })).toBeEnabled());
    expect(screen.queryByText('已中断该执行记录，后续步骤已跳过')).toBeNull();
  });

  it('请求返回前重复点击只发送一次中断请求', async () => {
    runs = [runningRun()];
    let resolveCancel: ((value: WorkflowRun) => void) | undefined;
    mockedWorkflowApi.cancelRun.mockImplementation(
      () => new Promise<WorkflowRun>((resolve) => {
        resolveCancel = (value: WorkflowRun) => {
          runs = runs.map(run => (run.run_id === value.run_id ? { ...run, status: 'cancelled' } : run));
          resolve(value);
        };
      }),
    );
    await renderPage();
    await screen.findAllByText(/手机1 ·/);

    const button = screen.getByRole('button', { name: '中断' });
    fireEvent.click(button);
    fireEvent.click(button);
    fireEvent.click(button);

    expect(mockedWorkflowApi.cancelRun).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: '中断中' })).toBeDisabled();

    resolveCancel?.(runs[0]);
    await screen.findByText('已中断该执行记录，后续步骤已跳过');
    await waitFor(() => expect(screen.queryByRole('button', { name: '中断中' })).toBeNull());
    expect(mockedWorkflowApi.cancelRun).toHaveBeenCalledTimes(1);
  });
});

describe('WorkflowPage 错误策略选择', () => {
  it('新建流程默认选中「错误后停止」', async () => {
    await renderPage();

    fireEvent.click(screen.getByRole('button', { name: '新建流程' }));

    const stopRadio = screen.getByRole('radio', { name: '错误后停止' }) as HTMLInputElement;
    const skipRadio = screen.getByRole('radio', {
      name: '错误后跳过错误脚本，后续继续其他脚本',
    }) as HTMLInputElement;
    expect(stopRadio.checked).toBe(true);
    expect(skipRadio.checked).toBe(false);
  });

  it('选择「错误后跳过错误脚本」保存时提交 continue_on_error=true', async () => {
    (scriptApi.getScripts as jest.Mock).mockResolvedValue({
      scripts: [{ script_id: 'script-1', name: '脚本一', platform: 'android' }],
    });
    mockedWorkflowApi.createWorkflow.mockResolvedValue({
      ...workflow,
      workflow_id: 'wf-new',
      continue_on_error: true,
    });
    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: '新建流程' }));
    await screen.findByText('可选脚本（1）');

    fireEvent.click(screen.getByRole('button', { name: /脚本一/ }));
    fireEvent.change(screen.getByPlaceholderText('例如：网盘批量转存'), {
      target: { value: '我的流程' },
    });
    fireEvent.click(screen.getByRole('radio', {
      name: '错误后跳过错误脚本，后续继续其他脚本',
    }));
    fireEvent.click(screen.getByRole('button', { name: '保存流程' }));

    await waitFor(() =>
      expect(mockedWorkflowApi.createWorkflow).toHaveBeenCalledWith(
        expect.objectContaining({
          name: '我的流程',
          script_ids: ['script-1'],
          continue_on_error: true,
        }),
      ),
    );
  });

  it('编辑已开启跳过的流程时回显「错误后跳过错误脚本」', async () => {
    mockedWorkflowApi.getWorkflows.mockResolvedValue({
      workflows: [{ ...workflow, continue_on_error: true }],
    });
    await renderPage();

    fireEvent.click(await screen.findByTitle('编辑流程'));

    const skipRadio = screen.getByRole('radio', {
      name: '错误后跳过错误脚本，后续继续其他脚本',
    }) as HTMLInputElement;
    const stopRadio = screen.getByRole('radio', { name: '错误后停止' }) as HTMLInputElement;
    expect(skipRadio.checked).toBe(true);
    expect(stopRadio.checked).toBe(false);
  });
});