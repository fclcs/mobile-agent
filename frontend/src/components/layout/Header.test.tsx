import { render, screen } from '@testing-library/react';
import { Header } from './Header';

describe('Header', () => {
  it('显示平台名与调度状态', () => {
    render(<Header />);
    expect(screen.getByText('Mobile Agent')).toBeInTheDocument();
    expect(screen.getByText('设备自动化调度')).toBeInTheDocument();
  });

  it('渲染通知按钮', () => {
    render(<Header />);
    const bell = screen.getByTitle('通知');
    expect(bell).toBeInTheDocument();
  });
});