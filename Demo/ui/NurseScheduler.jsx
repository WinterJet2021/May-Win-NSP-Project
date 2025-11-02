import React, { useState, useEffect, useRef } from 'react';
import Chart from 'chart.js/auto';
import Papa from 'papaparse';

// Shift color styles
const shiftStyles = {
  M: { backgroundColor: '#e3f2fd' }, // Morning
  A: { backgroundColor: '#fff8e1' }, // Afternoon/Evening
  N: { backgroundColor: '#e8f5e9' }, // Night
  OFF: { backgroundColor: '#f5f5f5' },
};

// Initial data structure
const initialData = {
  nurses: [],
  shifts: ['M', 'A', 'N'],
  dates: [],
  coverage: [],
  assignments: [],
  shortfall: []
};

const ShiftLegend = () => (
  <div className="flex gap-4 text-sm my-2">
    <div className="flex items-center">
      <div className="w-4 h-4 mr-1" style={shiftStyles.M}></div> Morning (M)
    </div>
    <div className="flex items-center">
      <div className="w-4 h-4 mr-1" style={shiftStyles.A}></div> Afternoon (A)
    </div>
    <div className="flex items-center">
      <div className="w-4 h-4 mr-1" style={shiftStyles.N}></div> Night (N)
    </div>
    <div className="flex items-center">
      <div className="w-4 h-4 mr-1" style={shiftStyles.OFF}></div> Off
    </div>
    <div className="flex items-center">
      <div className="w-4 h-4 mr-1 bg-red-100"></div> Shortfall
    </div>
  </div>
);

/** Validator banner to loudly flag any real gaps (optional but helpful) */
function CoverageValidator({ data }) {
  if (!data?.dates?.length) return null;

  const need = {};
  (data.coverage || []).forEach(c => {
    const k = `${c.date}-${c.shift}`;
    need[k] = (need[k] || 0) + Number(c.req_total || 0);
  });

  const got = {};
  (data.assignments || []).forEach(a => {
    const k = `${a.date}-${a.shift}`;
    got[k] = (got[k] || 0) + 1;
  });

  const misses = Object.keys(need).filter(k => (got[k] || 0) < need[k]);
  if (!misses.length) return null;

  return (
    <div className="bg-red-50 text-red-800 border border-red-200 rounded p-3 mb-4 text-sm">
      Some requirements were not met:
      <ul className="list-disc pl-5">
        {misses.slice(0, 12).map(k => (
          <li key={k}>
            {k} → need {need[k]}, got {got[k] || 0}
          </li>
        ))}
      </ul>
      {misses.length > 12 && <div>…and {misses.length - 12} more.</div>}
    </div>
  );
}

/** Union-aware schedule table (renders all nurses that appear in assignments) */
function ScheduleTable({ data }) {
  if (!data?.dates?.length) return null;

  // Map known nurse meta
  const nurseMeta = {};
  (data.nurses || []).forEach(n => { if (n?.id) nurseMeta[n.id] = n; });

  // Union of nurse IDs from nurses[] + assignments[]
  const allIds = Array.from(new Set([
    ...(data.nurses || []).map(n => n.id),
    ...(data.assignments || []).map(a => a.nurse_id),
  ])).filter(Boolean).sort();

  // Fast lookups
  const assignmentMap = {};
  (data.assignments || []).forEach(a => {
    assignmentMap[`${a.nurse_id}-${a.date}`] = a.shift;
  });

  const shortfallMap = {};
  (data.shortfall || []).forEach(s => {
    shortfallMap[`${s.date}-${s.shift}`] = s.unmet;
  });

  return (
    <div className="overflow-x-auto">
      <ShiftLegend />
      <table className="min-w-full bg-white border border-gray-300">
        <thead>
          <tr className="bg-gray-100">
            <th className="py-2 px-4 border">Nurse</th>
            {data.dates.map(date => (
              <th key={date} className="py-2 px-4 border text-sm">
                {new Date(date).toLocaleDateString('en-US', {
                    month: 'short', day: 'numeric', weekday: 'short'
                })}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {allIds.map(nid => {
            const n = nurseMeta[nid] || { id: nid, name: nid };
            return (
              <tr key={nid}>
                <td className="py-2 px-4 border font-medium">{n.id}</td>
                {data.dates.map(date => {
                  const shift = assignmentMap[`${nid}-${date}`] || 'OFF';
                  return (
                    <td
                      key={date}
                      className="py-2 px-4 border text-center"
                      style={shiftStyles[shift]}
                    >
                      {shift !== 'OFF' ? shift : ''}
                    </td>
                  );
                })}
              </tr>
            );
          })}
          <tr className="bg-gray-50">
            <td className="py-2 px-4 border font-bold">Coverage</td>
            {data.dates.map(date => {
              const dayShortfalls = [];
              (data.shifts || []).forEach(shift => {
                const key = `${date}-${shift}`;
                if (shortfallMap[key]) dayShortfalls.push(`${shift}: -${shortfallMap[key]}`);
              });
              return (
                <td
                  key={date}
                  className={`py-2 px-4 border text-center text-sm ${dayShortfalls.length ? 'bg-red-100' : ''}`}
                >
                  {dayShortfalls.length ? dayShortfalls.join(', ') : 'OK'}
                </td>
              );
            })}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function CoverageChart({ data }) {
  const chartRef = useRef(null);
  const chartInstance = useRef(null);

  useEffect(() => {
    if (!data.dates.length) return;

    // Count assignments per shift per date
    const shiftCounts = {};
    data.dates.forEach(date => { shiftCounts[date] = { M: 0, A: 0, N: 0 }; });
    (data.assignments || []).forEach(a => { shiftCounts[a.date][a.shift]++; });

    // Requirements map
    const requirements = {};
    (data.coverage || []).forEach(c => {
      if (!requirements[c.date]) requirements[c.date] = {};
      requirements[c.date][c.shift] = c.req_total;
    });

    const chartData = {
      labels: data.dates.map(date =>
        new Date(date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
      ),
      datasets: [
        { label: 'Morning (M)',   data: data.dates.map(d => shiftCounts[d]['M']), backgroundColor: '#bbdefb', borderColor: '#2196f3', borderWidth: 1, stack: 'S' },
        { label: 'Afternoon (A)', data: data.dates.map(d => shiftCounts[d]['A']), backgroundColor: '#ffe0b2', borderColor: '#ff9800', borderWidth: 1, stack: 'S' },
        { label: 'Night (N)',     data: data.dates.map(d => shiftCounts[d]['N']), backgroundColor: '#c8e6c9', borderColor: '#4caf50', borderWidth: 1, stack: 'S' },
        { label: 'M Required', data: data.dates.map(d => requirements[d]?.['M'] || 0), type: 'line', borderColor: '#1565c0', borderWidth: 2, fill: false, pointRadius: 3 },
        { label: 'A Required', data: data.dates.map(d => requirements[d]?.['A'] || 0), type: 'line', borderColor: '#ef6c00', borderWidth: 2, fill: false, pointRadius: 3 },
        { label: 'N Required', data: data.dates.map(d => requirements[d]?.['N'] || 0), type: 'line', borderColor: '#2e7d32', borderWidth: 2, fill: false, pointRadius: 3 },
      ]
    };

    if (chartInstance.current) chartInstance.current.destroy();
    const ctx = chartRef.current.getContext('2d');
    chartInstance.current = new Chart(ctx, {
      type: 'bar',
      data: chartData,
      options: {
        responsive: true, maintainAspectRatio: false,
        scales: {
          y: { beginAtZero: true, title: { display: true, text: 'Number of Nurses' } },
          x: { title: { display: true, text: 'Date' } }
        },
        plugins: {
          title: { display: true, text: 'Nurse Coverage vs. Requirements', font: { size: 16 } },
          tooltip: { mode: 'index', intersect: false }
        }
      }
    });

    return () => { if (chartInstance.current) chartInstance.current.destroy(); };
  }, [data]);

  return <div className="h-80 mt-6"><canvas ref={chartRef}></canvas></div>;
}

function FileUploader({ onDataLoaded, apiBaseUrl = '' }) {
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState('');
  const fileInputRef = useRef(null);

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setIsUploading(true);
    setError('');
    const formData = new FormData();
    formData.append('file', file);

    fetch(`${apiBaseUrl}/api/upload`, { method: 'POST', body: formData })
      .then(r => r.json())
      .then(d => { if (d.error) throw new Error(d.error); onDataLoaded(d); })
      .catch(err => setError(err.message || 'Error uploading file'))
      .finally(() => setIsUploading(false));
  };

  const loadSampleData = () => {
    setIsUploading(true);
    setError('');
    fetch(`${apiBaseUrl}/api/sample`)
      .then(r => r.json())
      .then(d => { if (d.error) throw new Error(d.error); onDataLoaded(d); })
      .catch(err => setError(err.message || 'Error loading sample data'))
      .finally(() => setIsUploading(false));
  };

  return (
    <div className="mb-6">
      <div className="flex flex-col sm:flex-row gap-4 mb-4">
        <input type="file" ref={fileInputRef} onChange={handleFileUpload} accept=".json" className="hidden" />
        <button onClick={() => fileInputRef.current?.click()} disabled={isUploading}
          className="bg-blue-600 hover:bg-blue-700 text-white py-2 px-4 rounded shadow transition">
          {isUploading ? 'Processing...' : 'Upload Schedule Data'}
        </button>
        <button onClick={loadSampleData} disabled={isUploading}
          className="bg-gray-600 hover:bg-gray-700 text-white py-2 px-4 rounded shadow transition">
          Load Sample Data
        </button>
      </div>
      {error && <div className="bg-red-100 text-red-700 p-3 rounded mb-4">{error}</div>}
    </div>
  );
}

function ScheduleExport({ data }) {
  const exportCSV = (type) => {
    let csvData, filename;
    if (type === 'assignments') {
      csvData = Papa.unparse({ fields: ['date', 'shift', 'nurse_id'], data: data.assignments });
      filename = 'assignments.csv';
    } else {
      csvData = Papa.unparse({ fields: ['date', 'shift', 'unmet'], data: data.shortfall });
      filename = 'shortfalls.csv';
    }
    const blob = new Blob([csvData], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = Object.assign(document.createElement('a'), { href: url, download: filename, style: 'visibility:hidden' });
    document.body.appendChild(link); link.click(); document.body.removeChild(link);
  };

  return (
    <div className="my-4 flex flex-wrap gap-3">
      <button onClick={() => exportCSV('assignments')}
        className="bg-green-600 hover:bg-green-700 text-white py-2 px-4 rounded shadow transition"
        disabled={!data.assignments.length}>Export Assignments</button>
      <button onClick={() => exportCSV('shortfalls')}
        className="bg-yellow-600 hover:bg-yellow-700 text-white py-2 px-4 rounded shadow transition"
        disabled={!data.shortfall.length}>Export Shortfalls</button>
    </div>
  );
}

function SolverControls({ onOptimize, filePath, disabled, apiBaseUrl = '' }) {
  const [timeLimit, setTimeLimit] = useState(60);
  const [threads, setThreads] = useState(8);
  const [isOptimizing, setIsOptimizing] = useState(false);
  const [progress, setProgress] = useState({ status: 'idle', message: '', percent: 0 });
  const statusCheckInterval = useRef(null);

  const handleOptimize = () => {
    setIsOptimizing(true);
    fetch(`${apiBaseUrl}/api/solve`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath, time_limit: timeLimit, threads: threads })
    })
      .then(r => r.json())
      .then(d => {
        if (d.error) throw new Error(d.error);
        statusCheckInterval.current = setInterval(checkStatus, 1000);
      })
      .catch(err => { console.error('Error starting optimization:', err); setIsOptimizing(false); });
  };

  const checkStatus = () => {
    fetch(`${apiBaseUrl}/api/status`)
      .then(r => r.json())
      .then(d => {
        setProgress(d);
        if (d.status === 'completed' || d.status === 'error') {
          clearInterval(statusCheckInterval.current);
          setIsOptimizing(false);
          if (d.status === 'completed') onOptimize();
        }
      })
      .catch(err => {
        console.error('Error checking status:', err);
        clearInterval(statusCheckInterval.current);
        setIsOptimizing(false);
      });
  };

  useEffect(() => () => { if (statusCheckInterval.current) clearInterval(statusCheckInterval.current); }, []);

  return (
    <div className="bg-white shadow rounded p-4 mb-6">
      <h2 className="text-lg font-bold mb-3">Solver Configuration</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <div>
          <label className="block text-sm font-medium mb-1">Time Limit (seconds)</label>
          <input type="number" value={timeLimit} onChange={(e) => setTimeLimit(e.target.value)}
            min="1" max="600" className="w-full border rounded py-2 px-3 text-gray-700" disabled={isOptimizing} />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Threads</label>
          <input type="number" value={threads} onChange={(e) => setThreads(e.target.value)}
            min="1" max="32" className="w-full border rounded py-2 px-3 text-gray-700" disabled={isOptimizing} />
        </div>
      </div>

      {isOptimizing && (
        <div className="mb-4">
          <div className="flex justify-between mb-1">
            <span className="text-sm font-medium">{progress.message}</span>
            <span className="text-sm font-medium">{progress.percent}%</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2.5">
            <div className="bg-blue-600 h-2.5 rounded-full" style={{ width: `${progress.percent}%` }}></div>
          </div>
        </div>
      )}

      <button onClick={handleOptimize} disabled={isOptimizing || disabled}
        className="bg-indigo-600 hover:bg-indigo-700 text-white py-2 px-6 rounded shadow transition disabled:bg-indigo-300">
        {isOptimizing ? 'Optimizing...' : 'Run Optimization'}
      </button>
    </div>
  );
}

export function NurseSchedulerApp({ apiBaseUrl = '' }) {
  const [scheduleData, setScheduleData] = useState(initialData);
  const [fileMetadata, setFileMetadata] = useState(null);
  const [objectiveValue, setObjectiveValue] = useState(null);
  const [dataLoaded, setDataLoaded] = useState(false);

  const handleDataLoaded = (data) => {
    setFileMetadata(data);
    fetchSolution();
  };

  const fetchSolution = () => {
    fetch(`${apiBaseUrl}/api/solution`)
      .then(r => { if (!r.ok && r.status !== 404) throw new Error('Network error'); return r.json(); })
      .then(d => {
        if (d?.error) return;
        setScheduleData(d);
        setObjectiveValue(d.objective);
        setDataLoaded(true);
      })
      .catch(err => console.error('Error fetching solution:', err));
  };

  return (
    <div className="container mx-auto px-4 py-8 max-w-7xl">
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-gray-800">Nurse Scheduling System</h1>
        <p className="text-gray-600 mt-2">Optimize schedules while meeting coverage & preferences</p>
      </header>

      <FileUploader onDataLoaded={handleDataLoaded} apiBaseUrl={apiBaseUrl} />

      {fileMetadata && (
        <div className="bg-white shadow rounded p-4 mb-6">
          <h2 className="text-lg font-bold mb-2">Dataset Information</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="bg-gray-50 p-3 rounded">
              <div className="text-sm text-gray-600">Nurses</div>
              <div className="text-lg font-bold">{fileMetadata.nurses}</div>
            </div>
            <div className="bg-gray-50 p-3 rounded">
              <div className="text-sm text-gray-600">Coverage Requirements</div>
              <div className="text-lg font-bold">{fileMetadata.coverage_requirements}</div>
            </div>
          </div>

          <SolverControls
            onOptimize={fetchSolution}
            filePath={fileMetadata.file_path}
            disabled={!fileMetadata.file_path}
            apiBaseUrl={apiBaseUrl}
          />
        </div>
      )}

      {dataLoaded && (
        <>
          {typeof objectiveValue === 'number' && (
            <div className="bg-white shadow rounded p-4 mb-6">
              <h2 className="text-lg font-bold mb-2">Solution Summary</h2>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="bg-blue-50 p-3 rounded">
                  <div className="text-sm text-blue-800">Objective Value</div>
                  <div className="text-2xl font-bold">{objectiveValue.toFixed(2)}</div>
                </div>
                <div className="bg-green-50 p-3 rounded">
                  <div className="text-sm text-green-800">Total Assignments</div>
                  <div className="text-2xl font-bold">{scheduleData.assignments.length}</div>
                </div>
                <div className="bg-red-50 p-3 rounded">
                  <div className="text-sm text-red-800">Days with Shortfall</div>
                  <div className="text-2xl font-bold">
                    {new Set(scheduleData.shortfall.filter(s => (s.unmet || 0) > 0).map(s => s.date)).size}
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className="bg-white shadow rounded p-4 mb-6">
            <CoverageValidator data={scheduleData} />
            <h2 className="text-lg font-bold mb-4">Schedule Visualization</h2>
            <ScheduleTable data={scheduleData} />
          </div>

          <div className="bg-white shadow rounded p-4 mb-6">
            <h2 className="text-lg font-bold mb-4">Coverage Analysis</h2>
            <CoverageChart data={scheduleData} />
          </div>

          <ScheduleExport data={scheduleData} />
        </>
      )}
    </div>
  );
}

// Export individual components for flexibility
export { ScheduleTable, CoverageChart, FileUploader, SolverControls, ScheduleExport };