import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/layout/Layout';
import { Dashboard } from './pages/Dashboard/Dashboard';
import { TaskPage } from './pages/Task/TaskPage';
import { ScriptPage } from './pages/Script/ScriptPage';
import { DevicePage } from './pages/Device/DevicePage';
import { WorkflowPage } from './pages/Workflow/WorkflowPage';
import { ScreenshotPage } from './pages/Workflow/ScreenshotPage';
import { ReportPage } from './pages/Report/ReportPage';
import { SettingsPage } from './pages/Settings/SettingsPage';
import { RescuePage } from './pages/Rescue/RescuePage';
import './styles/globals.css';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="tasks" element={<TaskPage />} />
          <Route path="scripts" element={<ScriptPage />} />
          <Route path="devices" element={<DevicePage />} />
          <Route path="workflows" element={<WorkflowPage />} />
          <Route path="screenshots" element={<ScreenshotPage />} />
          <Route path="reports" element={<ReportPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="rescue" element={<RescuePage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
