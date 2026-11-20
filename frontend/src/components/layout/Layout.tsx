import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';

export function Layout() {
  return (
    <div className="min-h-screen bg-[#F7F5F1]">
      {/* Sidebar */}
      <Sidebar />

      {/* Header */}
      <Header />

      {/* Main Content */}
      <main className="ml-[var(--sidebar-w,14rem)] pt-14 min-h-screen transition-[margin] duration-200">
        <div className="p-5">
          <Outlet />
        </div>
      </main>
    </div>
  );
}