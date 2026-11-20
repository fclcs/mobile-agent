import { render, screen, fireEvent } from '@testing-library/react';
import { Sidebar } from './Sidebar';
import { MemoryRouter } from 'react-router-dom';

const renderSidebar = () =>
  render(
    <MemoryRouter initialEntries={['/']}>
      <Sidebar />
    </MemoryRouter>
  );

describe('Sidebar', () => {
  it('展开时显示品牌名与副标题', () => {
    renderSidebar();
    expect(screen.getByText('Mobile Agent')).toBeInTheDocument();
    expect(screen.getByText('automation console')).toBeInTheDocument();
  });

  it('点击收起按钮后隐藏文字、再点恢复', () => {
    renderSidebar();
    const toggle = screen.getByLabelText('收起侧边栏');
    fireEvent.click(toggle);
    expect(screen.queryByText('Mobile Agent')).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('展开侧边栏'));
    expect(screen.getByText('Mobile Agent')).toBeInTheDocument();
  });

  it('只保留现役菜单，已下线页面不出现在导航里', () => {
    renderSidebar();
    const labels = [
      '仪表盘',
      '手机管理',
      '脚本管理',
      '流程管理',
      '脚本救援',
      '执行中心',
      '任务管理',
      '截图记录',
      '报告管理',
      '模型配置',
    ];
    labels.forEach((label) => {
      expect(screen.getByText(label)).toBeInTheDocument();
    });
    ['项目管理', 'APK管理', 'AI Agent', '资源管理'].forEach((label) => {
      expect(screen.queryByText(label)).not.toBeInTheDocument();
    });
  });

  it('当前路由对应的菜单项带琥珀选中态', () => {
    renderSidebar();
    const dashboard = screen.getByText('仪表盘');
    const link = dashboard.closest('a');
    expect(link?.className).toContain('border-[#F2A33A]');
  });

  it('底部显示版本号', () => {
    renderSidebar();
    expect(screen.getByText('v1.0.0')).toBeInTheDocument();
  });
});