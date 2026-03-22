export const API_BASE = 'http://127.0.0.1:8000/api';
export const WS_BASE = 'ws://127.0.0.1:8000/ws';

export const SPINNER = ['/', '-', '\\', '|'];

export const IMPACT_PRIORITY = {
  'ph5b': 1,
  'ph5-merge': 2,
  'boundary': 3,
  'sequence': 4,
  'orphan': 5,
  'internal': 6,
};

export const IMPACT_LABELS = {
  'ph5b': { label: 'Ph5b', color: 'text-red-400 bg-red-400/10' },
  'ph5-merge': { label: 'Fusión', color: 'text-orange-400 bg-orange-400/10' },
  'boundary': { label: 'Frontera', color: 'text-yellow-400 bg-yellow-400/10' },
  'sequence': { label: 'Secuencia', color: 'text-red-400 bg-red-400/10' },
  'orphan': { label: 'Huérfana', color: 'text-red-400 bg-red-400/10' },
  'high': { label: 'Alcance/Alta', color: 'text-red-400 bg-red-400/10' },
  'internal': { label: 'Interna', color: 'text-gray-500 bg-gray-500/10' },
};

export const formatTime = (seconds) => {
  if (!seconds || isNaN(seconds)) return "00:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
};
