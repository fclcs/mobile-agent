import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ScriptPage } from './ScriptPage';
import { scriptApi } from '../../services/api';
import type { Script } from '../../stores/agentStore';

jest.mock('../../services/api', () => ({
  scriptApi: {
    getScripts: jest.fn(),
    getScript: jest.fn(),
    updateScript: jest.fn(),
    deleteScript: jest.fn(),
    executeScript: jest.fn(),
  },
  deviceApi: { getDevices: jest.fn() },
  taskApi: { createTask: jest.fn(), executeTask: jest.fn() },
}));

jest.mock('react-router-dom', () => ({
  useNavigate: () => jest.fn(),
}));

const mockedScriptApi = scriptApi as unknown as {
  getScripts: jest.Mock;
  updateScript: jest.Mock;
};

let scripts: Script[];

function makeScript(overrides: Partial<Script> = {}): Script {
  return {
    script_id: 'script-1',
    name: '原有名称',
    description: '测试脚本',
    platform: 'android',
    script_type: 'external',
    content: 'print("hello")\n',
    status: 'saved',
    created_at: '2026-11-15T10:00:00',
    updated_at: '2026-11-15T10:00:00',
    version: 2,
    ...overrides,
  };
}

async function renderPage() {
  render(<ScriptPage />);
  await screen.findByText(scripts[0].name);
}

function openEditModal() {
  fireEvent.click(screen.getByTitle('编辑脚本名称'));
  return screen.getByPlaceholderText('输入脚本名称') as HTMLInputElement;
}

beforeEach(() => {
  jest.clearAllMocks();
  scripts = [makeScript()];
  (mockedScriptApi.getScripts as jest.Mock).mockImplementation(async () => ({ scripts }));
  mockedScriptApi.updateScript.mockImplementation(async (scriptId: string, data: { name?: string; content?: string }) => {
    scripts = scripts.map(script => (
      script.script_id === scriptId
        ? {
          ...script,
          name: data.name ?? script.name,
          content: data.content ?? script.content,
          version: data.content ? script.version + 1 : script.version,
        }
        : script
    ));
    return scripts[0];
  });
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe('ScriptPage 脚本重命名', () => {
  it('修改名称后只提交 name 字段，列表刷新为新名称', async () => {
    await renderPage();
    const input = openEditModal();
    expect(input.value).toBe('原有名称');

    fireEvent.change(input, { target: { value: '  新名称  ' } });
    fireEvent.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() => expect(mockedScriptApi.updateScript).toHaveBeenCalledTimes(1));
    expect(mockedScriptApi.updateScript).toHaveBeenCalledWith('script-1', { name: '新名称' });
    await screen.findByText('脚本名称已更新');
    await screen.findByText('新名称');
    expect(screen.queryByText('编辑脚本')).toBeNull();
  });

  it('名称为空时提示错误且不请求接口，弹窗保持打开', async () => {
    await renderPage();
    const input = openEditModal();

    fireEvent.change(input, { target: { value: '   ' } });
    fireEvent.click(screen.getByRole('button', { name: '保存' }));

    await screen.findByText('脚本名称不能为空');
    expect(mockedScriptApi.updateScript).not.toHaveBeenCalled();
    expect(screen.getByText('编辑脚本')).toBeInTheDocument();
  });

  it('名称超过 100 个字符时提示长度错误', async () => {
    await renderPage();
    const input = openEditModal();

    fireEvent.change(input, { target: { value: 'x'.repeat(101) } });
    fireEvent.click(screen.getByRole('button', { name: '保存' }));

    await screen.findByText('脚本名称最多 100 个字符');
    expect(mockedScriptApi.updateScript).not.toHaveBeenCalled();
  });

  it('接口失败时保留输入内容并显示后端错误信息', async () => {
    const failure = Object.assign(new Error('Request failed'), {
      response: { data: { detail: '脚本不存在' } },
    });
    mockedScriptApi.updateScript.mockRejectedValueOnce(failure);
    await renderPage();
    const input = openEditModal();

    fireEvent.change(input, { target: { value: '改成失败' } });
    fireEvent.click(screen.getByRole('button', { name: '保存' }));

    await screen.findByText('保存失败：脚本不存在');
    expect(input.value).toBe('改成失败');
    expect(screen.getByText('编辑脚本')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '保存' })).toBeEnabled();
  });

  it('只修改内容时提交 content 字段，名称不变也允许保存', async () => {
    await renderPage();
    openEditModal();
    const textarea = screen.getByPlaceholderText('输入脚本内容...') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: 'print("updated")\n' } });
    fireEvent.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() => expect(mockedScriptApi.updateScript).toHaveBeenCalledTimes(1));
    expect(mockedScriptApi.updateScript).toHaveBeenCalledWith('script-1', {
      content: 'print("updated")\n',
    });
    await screen.findByText('脚本编辑成功');
  });

  it('名称和内容都未改动时直接关闭弹窗，不发请求', async () => {
    await renderPage();
    openEditModal();
    fireEvent.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() => expect(screen.queryByText('编辑脚本')).toBeNull());
    expect(mockedScriptApi.updateScript).not.toHaveBeenCalled();
  });
});