// Demo/ui/NurseSchedulerDemo.jsx

import React from 'react';
import { useState, useEffect } from 'react';

// Shift color styles
const shiftStyles = {
  D: { backgroundColor: '#e3f2fd' },
  E: { backgroundColor: '#fff8e1' },
  N: { backgroundColor: '#e8f5e9' },
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
  shifts: ["D", "E", "N"],
  dates: ["2023-10-01", "2023-10-02", "2023-10-03", "2023-10-04", "2023-10-05", "2023-10-06", "2023-10-07"],
  coverage: [
    { date: "2023-10-01", shift: "D", req_total: 2 },
    { date: "2023-10-01", shift: "E", req_total: 1 },
    { date: "2023-10-01", shift: "N", req_total: 1 },
    { date: "2023-10-02", shift: "D", req_total: 2 },
    { date: "2023-10-02", shift: "E", req_total: 2 },
    { date: "2023-10-02", shift: "N", req_total: 1 },
    { date: "2023-10-03", shift: "D", req_total: 3 },
    { date: "2023-10-03", shift: "E", req_total: 2 },
    { date: "2023-10-03", shift: "N", req_total: 1 },
    { date: "2023-10-04", shift: "D", req_total: 3 },
    { date: "2023-10-04", shift: "E", req_total: 2 },
    { date: "2023-10-04", shift: "N", req_total: 1 },
    { date: "2023-10-05", shift: "D", req_total: 2 },
    { date: "2023-10-05", shift: "E", req_total: 2 },
    { date: "2023-10-05", shift: "N", req_total: 1 },
    { date: "2023-10-06", shift: "D", req_total: 2 },
    { date: "2023-10-06", shift: "E", req_total: 1 },
    { date: "2023-10-06", shift: "N", req_total: 1 },
    { date: "2023-10-07", shift: "D", req_total: 1 },
    { date: "2023-10-07", shift: "E", req_total: 1 },
    { date: "2023-10-07", shift: "N", req_total: 1 }
  ],
  assignments: [
    { date: "2023-10-01", shift: "D", nurse_id: "Nurse1" },
    { date: "2023-10-01", shift: "D", nurse_id: "Nurse2" },
    { date: "2023-10-01", shift: "E", nurse_id: "Nurse3" },
    { date: "2023-10-01", shift: "N", nurse_id: "Nurse5" },
    { date: "2023-10-02", shift: "D", nurse_id: "Nurse2" },
    { date: "2023-10-02", shift: "D", nurse_id: "Nurse4" },
    { date: "2023-10-02", shift: "E", nurse_id: "Nurse1" },
    { date: "2023-10-02", shift: "E", nurse_id: "Nurse5" },
    { date: "2023-10-02", shift: "N", nurse_id: "Nurse3" },
    { date: "2023-10-03", shift: "D", nurse_id: "Nurse1" },
    { date: "2023-10-03", shift: "D", nurse_id: "Nurse3" },
    { date: "2023-10-03", shift: "D", nurse_id: "Nurse5" },
    { date: "2023-10-03", shift: "E", nurse_id: "Nurse2" },
    { date: "2023-10-03", shift: "E", nurse_id: "Nurse4" },
    { date: "2023-10-03", shift: "N", nurse_id: "Nurse1" },
    { date: "2023-10-04", shift: "D", nurse_id: "Nurse2" },
    { date: "2023-10-04", shift: "D", nurse_id: "Nurse3" },
    { date: "2023-10-04", shift: "D", nurse_id: "Nurse4" },
    { date: "2023-10-04", shift: "E", nurse_id: "Nurse5" },
    { date: "2023-10-04", shift: "N", nurse_id: "Nurse1" },
    { date: "2023-10-05", shift: "D", nurse_id: "Nurse2" },
    { date: "2023-10-05", shift: "D", nurse_id: "Nurse5" },
    { date: "2023-10-05", shift: "E", nurse_id: "Nurse1" },
    { date: "2023-10-05", shift: "E", nurse_id: "Nurse3" },
    { date: "2023-10-05", shift: "N", nurse_id: "Nurse4" },
    { date: "2023-10-06", shift: "D", nurse_id: "Nurse1" },
    { date: "2023-10-06", shift: "D", nurse_id: "Nurse3" },
    { date: "2023-10-06", shift: "E", nurse_id: "Nurse2" },
    { date: "2023-10-06", shift: "N", nurse_id: "Nurse5" },
    { date: "2023-10-07", shift: "D", nurse_id: "Nurse4" },
    { date: "2023-10-07", shift: "E", nurse_id: "Nurse1" },
    { date: "2023-10-07", shift: "N", nurse_id: "Nurse3" }
  ],
  shortfall: [
    { date: "2023-10-04", shift: "E", unmet: 1 },
    { date: "2023-10-07", shift: "N", unmet: 0 }
  ],
  objective: 125.5
};

// ShiftLegend component
const ShiftLegend = () => (
  <div className="flex flex-wrap gap-4 text-sm my-2">
    <div className="flex items-center">
      <div className="w-4 h-4 mr-1" style={shiftStyles.D}></div> Day
    </div>
    <div className="flex items-center">
      <div className="w-4 h-4 mr-1" style={shiftStyles.E}></div> Evening
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

// Main component
const NurseScheduler = () => {
  const data = sampleData;
  const [tab, setTab] = useState('schedule'); // 'schedule' or 'coverage'
  
  // Create a mapping for quick lookup
  const assignmentMap = {};
  data.assignments.forEach(a => {
    const key = `${a.nurse_id}-${a.date}`;
    assignmentMap[key] = a.shift;
  });

  // Create shortfall map
  const shortfallMap = {};
  data.shortfall.forEach(s => {
    const key = `${s.date}-${s.shift}`;
    shortfallMap[key] = s.unmet;
  });
  
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
              {new Set(data.shortfall.map(s => s.date)).size}
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
                      month: 'short',
                      day: 'numeric',
                      weekday: 'short'
                    })}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.nurses.map(nurse => (
                <tr key={nurse.id}>
                  <td className="py-2 px-4 border font-medium">{nurse.id}</td>
                  {data.dates.map(date => {
                    const shift = assignmentMap[`${nurse.id}-${date}`] || 'OFF';
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
              
              {/* Coverage Requirements Row */}
              <tr className="bg-gray-50">
                <td className="py-2 px-4 border font-bold">Coverage</td>
                {data.dates.map(date => {
                  const dayShortfalls = [];
                  data.shifts.forEach(shift => {
                    const key = `${date}-${shift}`;
                    if (shortfallMap[key]) {
                      dayShortfalls.push(`${shift}: -${shortfallMap[key]}`);
                    }
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
                    {shift === 'D' ? 'Day' : shift === 'E' ? 'Evening' : 'Night'} Shift
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.dates.map(date => {
                // Count nurses assigned to each shift on this date
                const counts = { D: 0, E: 0, N: 0 };
                data.assignments.forEach(a => {
                  if (a.date === date) {
                    counts[a.shift]++;
                  }
                });
                
                // Get requirements
                const reqs = { D: 0, E: 0, N: 0 };
                data.coverage.forEach(c => {
                  if (c.date === date) {
                    reqs[c.shift] = c.req_total;
                  }
                });
                
                return (
                  <tr key={date}>
                    <td className="py-2 px-4 border font-medium">
                      {new Date(date).toLocaleDateString('en-US', {
                        month: 'short',
                        day: 'numeric',
                        weekday: 'short'
                      })}
                    </td>
                    {data.shifts.map(shift => {
                      const shortfall = (reqs[shift] > counts[shift]) ? reqs[shift] - counts[shift] : 0;
                      return (
                        <td 
                          key={shift} 
                          className={`py-2 px-4 border text-center ${shortfall ? 'bg-red-100' : ''}`}
                        >
                          <div className="font-bold">{counts[shift]} / {reqs[shift]}</div>
                          <div className="text-xs">
                            {shortfall > 0 ? `Shortfall: ${shortfall}` : 'Coverage Met'}
                          </div>
                          <div className="text-xs mt-1">
                            {data.assignments
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