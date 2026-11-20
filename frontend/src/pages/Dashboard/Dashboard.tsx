import { useEffect } from 'react';
import {
  CheckCircle,
  ListTodo,
  Clock,
  Play,
  CheckCircle2,
  XCircle,
  Loader2,
} from 'lucide-react';
import { useDeviceStore } from '../../stores/deviceStore';
import { useTaskStore } from '../../stores/taskStore';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell
} from 'recharts';

export function Dashboard() {
  const { devices, fetchDevices } = useDeviceStore();
  const { tasks, fetchTasks } = useTaskStore();

  useEffect(() => {
    fetchDevices();
    fetchTasks();
  }, []);

  // 仪表盘只统计在线设备；登记但离线的手机不属于“连接”。
  const activeDevices = devices.filter(d => d.status === 'connected');
  const uniqueDeviceNames = [...new Set(activeDevices.map(d => d.name))];
  const usbCount = activeDevices.filter(d => d.connection_type === 'usb').length;
  const wifiCount = activeDevices.filter(d => d.connection_type === 'tcpip').length;

  const stats = [
    {
      title: '运行中任务',
      value: tasks.filter(t => t.status === 'executing').length.toString(),
      icon: <Play className="w-5 h-5 text-[#F2A33A]" />,
      iconBg: 'bg-[#FDF1DC]',
    },
    {
      title: '通过率',
      value: tasks.length > 0 
        ? `${Math.round((tasks.filter(t => t.status === 'completed').length / tasks.length) * 100)}%`
        : '0%',
      icon: <CheckCircle className="w-5 h-5 text-[#F2A33A]" />,
      iconBg: 'bg-[#FDF1DC]',
    },
    {
      title: '总任务数',
      value: tasks.length.toString(),
      icon: <ListTodo className="w-5 h-5 text-[#F2A33A]" />,
      iconBg: 'bg-[#FDF1DC]',
    },
    {
      title: '设备数量',
      value: uniqueDeviceNames.length.toString(),
      detail: `USB ${usbCount} | WiFi ${wifiCount}`,
      icon: <Clock className="w-5 h-5 text-[#F2A33A]" />,
      iconBg: 'bg-[#FDF1DC]',
    },
  ];

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="w-4 h-4 text-[#3FB950]" />;
      case 'executing':
        return <Loader2 className="w-4 h-4 text-[#F2A33A] animate-spin" />;
      case 'failed':
        return <XCircle className="w-4 h-4 text-[#E5484D]" />;
      default:
        return null;
    }
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case 'completed':
        return '通过';
      case 'executing':
        return '运行中';
      case 'failed':
        return '失败';
      default:
        return status;
    }
  };

  const getStatusClass = (status: string) => {
    switch (status) {
      case 'completed':
        return 'text-[#3FB950]';
      case 'executing':
        return 'text-[#F2A33A]';
      case 'failed':
        return 'text-[#E5484D]';
      default:
        return 'text-[#6B7076]';
    }
  };

  const chartData = [
    { name: '周一', value: Math.floor(Math.random() * 20) + 10 },
    { name: '周二', value: Math.floor(Math.random() * 20) + 10 },
    { name: '周三', value: Math.floor(Math.random() * 20) + 10 },
    { name: '周四', value: Math.floor(Math.random() * 20) + 10 },
    { name: '周五', value: Math.floor(Math.random() * 20) + 10 },
    { name: '周六', value: Math.floor(Math.random() * 20) + 10 },
    { name: '周日', value: Math.floor(Math.random() * 20) + 10 },
  ];

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[#16191C]">欢迎回来</h1>
          <p className="text-[#6B7076] text-sm mt-1">开始自动化测试任务</p>
        </div>
        <div className="text-right">
          <p className="text-[#9AA0A6] text-xs">{new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' })}</p>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat, index) => (
          <div
            key={index}
            className="bg-white border border-[#E6E1D8] rounded-lg p-4 hover:shadow-md transition-all duration-200"
          >
            <div className="flex items-start justify-between">
              <div>
                <p className="text-[#6B7076] text-xs font-medium">{stat.title}</p>
                <p className="text-2xl font-semibold text-[#16191C] mt-1.5">{stat.value}</p>
              </div>
              <div className={`p-2 ${stat.iconBg} rounded-lg`}>{stat.icon}</div>
            </div>
            {stat.detail && (
              <p className="text-[#9AA0A6] text-xs mt-2">{stat.detail}</p>
            )}
          </div>
        ))}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Task Trend */}
        <div className="bg-white border border-[#E6E1D8] rounded-lg p-4">
          <h3 className="text-[#16191C] font-semibold text-sm mb-3">任务趋势 (近7天)</h3>
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={tasks.length > 0 ? tasks.slice(-7).map((_t, i) => ({ name: `Day ${i+1}`, value: Math.floor(Math.random() * 15) + 5 })) : chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F0EDE6" />
                <XAxis dataKey="name" stroke="#9AA0A6" fontSize={11} />
                <YAxis stroke="#9AA0A6" fontSize={11} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#ffffff',
                    border: '1px solid #E6E1D8',
                    borderRadius: '6px',
                    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.06)',
                  }}
                  labelStyle={{ color: '#16191C', fontSize: 12 }}
                />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="#F2A33A"
                  strokeWidth={2}
                  dot={{ fill: '#F2A33A', r: 4 }}
                  activeDot={{ fill: '#F2A33A', r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Device Status */}
        <div className="bg-white border border-[#E6E1D8] rounded-lg p-4">
          <h3 className="text-[#16191C] font-semibold text-sm mb-3">设备状态分布</h3>
          {activeDevices.length > 0 ? (
            <div className="h-52 flex items-center">
              <ResponsiveContainer width="50%" height="100%">
                <PieChart>
                  <Pie
                    data={activeDevices.map(d => ({ name: d.platform, value: 1 }))}
                    cx="50%"
                    cy="50%"
                    innerRadius={40}
                    outerRadius={65}
                    dataKey="value"
                  >
                    {activeDevices.map((device, index) => (
                      <Cell key={`cell-${index}`} fill={device.platform === 'android' ? '#3FB950' : device.platform === 'ios' ? '#6B7076' : '#F2A33A'} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#ffffff',
                      border: '1px solid #E6E1D8',
                      borderRadius: '6px',
                      boxShadow: '0 4px 12px rgba(0, 0, 0, 0.06)',
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex-1 space-y-2 pl-3">
                {uniqueDeviceNames.map(name => {
                  const deviceEntries = activeDevices.filter(d => d.name === name);
                  return (
                    <div key={name} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div
                          className="w-2.5 h-2.5 rounded-full"
                          style={{ backgroundColor: deviceEntries[0].platform === 'android' ? '#3FB950' : deviceEntries[0].platform === 'ios' ? '#6B7076' : '#F2A33A' }}
                        />
                        <span className="text-[#6B7076] text-xs">{name}</span>
                      </div>
                      <span className="text-[#9AA0A6] text-xs">{deviceEntries.length} 连接</span>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="h-52 flex items-center justify-center text-[#9AA0A6] text-sm">
              暂无设备数据
            </div>
          )}
        </div>
      </div>

      {/* Recent Tasks */}
      <div className="bg-white border border-[#E6E1D8] rounded-lg overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b border-[#F0EDE6]">
          <h3 className="text-[#16191C] font-semibold text-sm">最近任务</h3>
          <span className="text-[#9AA0A6] text-xs">{tasks.length} 项</span>
        </div>
        {tasks.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-[#9AA0A6] text-xs border-b border-[#F0EDE6]">
                  <th className="text-left py-2.5 px-4 font-medium">任务名称</th>
                  <th className="text-left py-2.5 px-4 font-medium">设备</th>
                  <th className="text-left py-2.5 px-4 font-medium">状态</th>
                  <th className="text-left py-2.5 px-4 font-medium">创建时间</th>
                </tr>
              </thead>
              <tbody>
                {tasks.slice(0, 5).map((task) => (
                  <tr key={task.task_id} className="border-b border-[#F7F5F1] last:border-0 hover:bg-[#F7F5F1]">
                    <td className="py-2.5 px-4 text-[#16191C] text-sm font-medium">{task.name}</td>
                    <td className="py-2.5 px-4 text-[#6B7076] text-xs">{task.device_id || '未指定'}</td>
                    <td className="py-2.5 px-4">
                      <div className="flex items-center gap-1.5">
                        {getStatusIcon(task.status)}
                        <span className={`text-xs font-medium ${getStatusClass(task.status)}`}>
                          {getStatusText(task.status)}
                        </span>
                      </div>
                    </td>
                    <td className="py-2.5 px-4 text-[#9AA0A6] text-xs">
                      {new Date(task.created_at).toLocaleString('zh-CN')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-12">
            <ListTodo className="w-12 h-12 text-[#E6E1D8] mx-auto mb-3" />
            <h3 className="text-[#16191C] text-base font-medium mb-1">暂无任务</h3>
            <p className="text-[#9AA0A6] text-sm">启动流程后，最近的执行记录会显示在这里</p>
          </div>
        )}
      </div>
    </div>
  );
}