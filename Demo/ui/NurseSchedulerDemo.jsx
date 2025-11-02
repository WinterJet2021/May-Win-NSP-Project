// Demo/ui/NurseSchedulerDemo.jsx

import React, { useState } from 'react';

// Shift color styles (align with main: M/A/N)
const shiftStyles = {
  M: { backgroundColor: '#e3f2fd' }, // Morning
  A: { backgroundColor: '#fff8e1' }, // Afternoon/Evening
  N: { backgroundColor: '#e8f5e9' }, // Night
  OFF: { backgroundColor: '#f5f5f5' },
};

// Sample data for demonstration
const sampleData = {
  nurses: [
    { id: "Nurse1", name: "John Doe" },
    { id: "Nurse2", name: "Jane Smith" },
    { id: "Nurse3", name: "Alice Johnson" },
    { id: "Nurse4", name: "Bob Williams" },
    { id: "Nurse5", name: "Carol Brown" }
  ],
  shifts: ["M", "A", "N"],
  dates: ["2023-10-01","2023-10-02","2023-10-03","2023-10-04","2023-10-05","2023-10-06","2023-10-07"],
  coverage: [
    { date: "2023-10-01", shift: "M", req_total: 2 },
    { date: "2023-10-01", shift: "A", req_total: 1 },
    { date: "2023-10-01", shift: "N", req_total: 1 },
    { date: "2023-10-02", shift: "M", req_total: 2 },
    { date: "2023-10-02", shift: "A", req_total: 2 },
    { date: "2023-10-02", shift: "N", req_total: 1 },
    { date: "2023-10-03", shift: "M", req_total: 3 },
    { date: "2023-10-03", shift: "A", req_total: 2 },
    { date: "2023-10-03", shift: "N", req_total: 1 },
    { date: "2023-10-04", shift: "M", req_total: 3 },
    { date: "2023-10-04", shift: "A", req_total: 2 },
    { date: "2023-10-04", shift: "N", req_total: 1 },
    { date: "2023-10-05", shift: "M", req_total: 2 },
    { date: "2023-10-05", shift: "A", req_total: 2 },
    { date: "2023-10-05", shift: "N", req_total: 1 },
    { date: "2023-10-06", shift: "M", req_total: 2 },
    { date: "2023-10-06", shift: "A", req_total: 1 },
    { date: "2023-10-06", shift: "N", req_total: 1 },
    { date: "2023-10-07", shift: "M", req_total: 1 },
    { date: "2023-10-07", shift: "A", req_total: 1 },
    { date: "2023-10-07", shift: "N", req_total: 1 }
  ],
  assignments: [
    { date: "2023-10-01", shift: "M", nurse_id: "Nurse1" },
    { date: "2023-10-01", shift: "M", nurse_id: "Nurse2" },
    { date: "2023-10-01", shift: "A", nurse_id: "Nurse3" },
    { date: "2023-10-01", shift: "N", nurse_id: "Nurse5" },
    { date: "2023-10-02", shift: "M", nurse_id: "Nurse2" },
    { date: "2023-10-02", shift: "M", nurse_id: "Nurse4" },
    { date: "2023-10-02", shift: "A", nurse_id: "Nurse1" },
    { date: "2023-10-02", shift: "A", nurse_id: "Nurse5" },
    { date: "2023-10-02", shift: "N", nurse_id: "Nurse3" },
    { date: "2023-10-03", shift: "M", nurse_id: "Nurse1" },
    { date: "2023-10-03", shift: "M", nurse_id: "Nurse3" },
    { date: "2023-10-03", shift: "M", nurse_id: "Nurse5" },
    { date: "2023-10-03", shift: "A", nurse_id: "Nurse2" },
    { date: "2023-10-03", shift: "A", nurse_id: "Nurse4" },
    { date: "2023-10-03", shift: "N", nurse_id: "Nurse1" },
    { date: "2023-10-04", shift: "M", nurse_id: "Nurse2" },
    { date: "2023-10-04", shift: "M", nurse_id: "Nurse3" },
    { date: "2023-10-04", shift: "M", nurse_id: "Nurse4" },
    { date: "2023-10-04", shift: "A", nurse_id: "Nurse5" },
    { date: "2023-10-04", shift: "N", nurse_id: "Nurse1" },
    { date: "2023-10-05", shift: "M", nurse_id: "Nurse2" },
    { date: "2023-10-05", shift: "M", nurse_id: "Nurse5" },
    { date: "2023-10-05", shift: "A", nurse_id: "Nurse1" },
    { date: "2023-10-05", shift: "A", nurse_id: "Nurse3" },
    { date: "2023-10-05", shift: "N", nurse_id: "Nurse4" },
    { date: "2023-10-06", shift: "M", nurse_id: "Nurse1" },
    { date: "2023-10-06", shift: "M", nurse_id: "Nurse3" },
    { date: "2023-10-06", shift: "A", nurse_id: "Nurse2" },
    { date: "2023-10-06", shift: "N", nurse_id: "Nurse5" },
    { date: "2023-10-07", shift: "M", nurse_id: "Nurse4" },
    { date: "2023-10-07", shift: "A", nurse_id: "Nurse1" },
    { date: "2023-10-07", shift: "N", nurse_id: "Nurse3" }
  ],
  shortfall: [
    { date: "2023-10-04", shift: "A", unmet: 1 },
    { date: "2023-10-07", shift: "N", unmet: 0 }
  ],
  objective: 125.5
};

const ShiftLegend = () => (
  <div className="flex flex-wrap gap-4 text-sm my-2">
    <div className="flex items-center">
      <div className="w-4 h-4 mr-1" style={shiftStyles.M}></div> Morning
    </div>
    <div className="flex items-center">
      <div className="w-4 h-4 mr-1" style={shiftStyles.A}></div> Afternoon
    </div>
    <div className="flex items-center">
      <div className="w-4 h-4 mr-1" style={shiftStyles.N}></div> Night
    </div>
    <div className="flex items-center">
      <div className="w-4 h-4 mr-1" style={shiftStyles.OFF}></div> Off
    </div>
    <div className="flex items-center">
      <div className="w-4 h-4 mr-1 bg-red-100"></div> Shortfall
    </div>
  </div>
);

function ensureMinNurses(nurses, min = 16) {
  const list = Array.isArray(nurses) ? [...nurses] : [];
  if (list.length >= min) return list;
  const needed = min - list.length;
  const base = list.length + 1;
  for (let i = 0; i < needed; i++) {
    const idx = base + i;
    list.push({ id: `Nurse${idx}`, name: `Nurse ${idx}` });
  }
  return list;
}

const NurseScheduler = () => {
  const data = { ...sampleData, nurses: ensureMinNurses(sampleData.nurses, 16) };
  const [tab, setTab] = useState('schedule');

  // Lookup maps
  const assignmentMap = {};
  (data.assignments || []).forEach(a => { assignmentMap[`${a.nurse_id}-${a.date}`] = a.shift; });
  const shortfallMap = {};
  (data.shortfall || []).forEach(s => { shortfallMap[`${s.date}-${s.shift}`] = s.unmet; });

  // Union-aware nurse list (demo shows same behavior as the real UI)
  const nurseMeta = {};
  (data.nurses || []).forEach(n => { if (n?.id) nurseMeta[n.id] = n; });
  const allIds = Array.from(new Set([
    ...(data.nurses || []).map(n => n.id),
    ...(data.assignments || []).map(a => a.nurse_id),
  ])).filter(Boolean).sort();

  return (
    <div className="max-w-full">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-800 mb-2">Nurse Scheduling System</h1>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-blue-50 p-3 rounded">
            <div className="text-sm text-blue-800">Objective Value</div>
            <div className="text-xl font-bold">{data.objective.toFixed(2)}</div>
          </div>
          <div className="bg-green-50 p-3 rounded">
            <div className="text-sm text-green-800">Total Assignments</div>
            <div className="text-xl font-bold">{data.assignments.length}</div>
          </div>
          <div className="bg-red-50 p-3 rounded">
            <div className="text-sm text-red-800">Days with Shortfall</div>
            <div className="text-xl font-bold">
              {new Set((data.shortfall || []).filter(s => (s.unmet || 0) > 0).map(s => s.date)).size}
            </div>
          </div>
        </div>
      </div>

      <div className="mb-4">
        <div className="flex border-b">
          <button
            className={`py-2 px-4 font-medium ${tab === 'schedule' ? 'border-b-2 border-blue-500 text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
            onClick={() => setTab('schedule')}
          >
            Schedule View
          </button>
          <button
            className={`py-2 px-4 font-medium ${tab === 'coverage' ? 'border-b-2 border-blue-500 text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
            onClick={() => setTab('coverage')}
          >
            Coverage View
          </button>
        </div>
      </div>

      {tab === 'schedule' && (
        <div className="overflow-x-auto">
          <ShiftLegend />
          <table className="min-w-full bg-white border border-gray-300">
            <thead>
              <tr className="bg-gray-100">
                <th className="py-2 px-4 border">Nurse</th>
                {data.dates.map(date => (
                  <th key={date} className="py-2 px-3 border text-sm">
                    {new Date(date).toLocaleDateString('en-US', {
                      month: 'short', day: 'numeric', weekday: 'short'
                    })}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {allIds.map(nid => (
                <tr key={nid}>
                  <td className="py-2 px-4 border font-medium">{nid}</td>
                  {data.dates.map(date => {
                    const shift = assignmentMap[`${nid}-${date}`] || 'OFF';
                    return (
                      <td
                        key={date}
                        className="py-2 px-3 border text-center"
                        style={shiftStyles[shift]}
                      >
                        {shift !== 'OFF' ? shift : ''}
                      </td>
                    );
                  })}
                </tr>
              ))}

              {/* Coverage row */}
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
                      className={`py-2 px-3 border text-center text-sm ${dayShortfalls.length ? 'bg-red-100' : ''}`}
                    >
                      {dayShortfalls.length ? dayShortfalls.join(', ') : 'OK'}
                    </td>
                  );
                })}
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {tab === 'coverage' && (
        <div className="overflow-x-auto">
          <table className="min-w-full bg-white border border-gray-300">
            <thead>
              <tr className="bg-gray-100">
                <th className="py-2 px-4 border">Date</th>
                {data.shifts.map(shift => (
                  <th key={shift} className="py-2 px-4 border text-center" style={shiftStyles[shift]}>
                    {shift === 'M' ? 'Morning' : shift === 'A' ? 'Afternoon' : 'Night'} Shift
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.dates.map(date => {
                // Count per shift
                const counts = { M: 0, A: 0, N: 0 };
                (data.assignments || []).forEach(a => { if (a.date === date) counts[a.shift]++; });
                // Requirements
                const reqs = { M: 0, A: 0, N: 0 };
                (data.coverage || []).forEach(c => { if (c.date === date) reqs[c.shift] = c.req_total; });

                return (
                  <tr key={date}>
                    <td className="py-2 px-4 border font-medium">
                      {new Date(date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', weekday: 'short' })}
                    </td>
                    {data.shifts.map(shift => {
                      const shortfall = (reqs[shift] > counts[shift]) ? reqs[shift] - counts[shift] : 0;
                      return (
                        <td key={shift} className={`py-2 px-4 border text-center ${shortfall ? 'bg-red-100' : ''}`}>
                          <div className="font-bold">{counts[shift]} / {reqs[shift]}</div>
                          <div className="text-xs">{shortfall > 0 ? `Shortfall: ${shortfall}` : 'Coverage Met'}</div>
                          <div className="text-xs mt-1">
                            {(data.assignments || [])
                              .filter(a => a.date === date && a.shift === shift)
                              .map(a => a.nurse_id)
                              .join(', ')}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-6 text-sm text-gray-600">
        <p>This is a demonstration of the nurse scheduling interface. In the full application, you can:</p>
        <ul className="list-disc ml-5 mt-2">
          <li>Upload scheduling data in JSON format</li>
          <li>Configure and run the Gurobi optimization solver</li>
          <li>View the results in interactive tables and charts</li>
          <li>Export the assignments and shortfalls as CSV files</li>
        </ul>
      </div>
    </div>
  );
};

export default NurseScheduler;
