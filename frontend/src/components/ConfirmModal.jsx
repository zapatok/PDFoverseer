import { useStore } from '../store/useStore';

export const ConfirmModal = () => {
  const config = useStore(s => s.confirmModal);
  const setConfirmModal = useStore(s => s.setConfirmModal);

  const onClose = () => {
    setConfirmModal({ ...config, isOpen: false });
  };

  if (!config.isOpen) return null;
  
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-[#1e1e2e] border border-[#313244] rounded-2xl p-6 shadow-2xl max-w-sm w-full mx-4 relative overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-accent to-success"></div>
        <h3 className="text-xl font-bold text-gray-200 mb-3">{config.title}</h3>
        <p className="text-gray-400 text-sm mb-6 leading-relaxed">{config.message}</p>
        <div className="flex justify-end space-x-3">
          {config.buttons ? (
            <>
              <button
                onClick={onClose}
                className="px-4 py-2 rounded-lg bg-surface hover:bg-white/5 text-gray-300 transition-colors text-sm font-medium border border-white/5"
              >
                Cancelar
              </button>
              {config.buttons.map((btn, idx) => (
                <button
                  key={idx}
                  onClick={() => {
                    if (btn.onClick) btn.onClick();
                    onClose();
                  }}
                  className={btn.className}
                >
                  {btn.label}
                </button>
              ))}
            </>
          ) : (
            <>
              {!config.isAlert && (
                <button
                  onClick={onClose}
                  className="px-4 py-2 rounded-lg bg-surface hover:bg-white/5 text-gray-300 transition-colors text-sm font-medium border border-white/5"
                >
                  Cancelar
                </button>
              )}
              <button
                onClick={() => {
                  if (config.onConfirm) config.onConfirm();
                  onClose();
                }}
                className="px-4 py-2 rounded-lg bg-accent text-base hover:opacity-90 font-bold transition-shadow shadow-[0_0_15px_rgba(137,180,250,0.3)] text-sm"
              >
                {config.isAlert ? 'Aceptar' : 'Confirmar'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
