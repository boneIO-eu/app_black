import { useTranslation } from '@/hooks/useTranslation';
import { FaPlus, FaTimes } from 'react-icons/fa';
import { NumericInput } from '@/components/ui/NumericInput';

interface SetBaseSectionProps {
  enableSetAddress: boolean;
  setEnableSetAddress: (value: boolean) => void;
  setAddressAddress: number;
  setSetAddressAddress: (value: number) => void;
  enableSetBaudrate: boolean;
  setEnableSetBaudrate: (value: boolean) => void;
  baudrateAddress: number;
  setBaudrateAddress: (value: number) => void;
  baudrateMappings: Record<string, number>;
  setBaudrateMappings: (value: Record<string, number>) => void;
}

export default function SetBaseSection({
  enableSetAddress,
  setEnableSetAddress,
  setAddressAddress,
  setSetAddressAddress,
  enableSetBaudrate,
  setEnableSetBaudrate,
  baudrateAddress,
  setBaudrateAddress,
  baudrateMappings,
  setBaudrateMappings,
}: SetBaseSectionProps) {
  const { t } = useTranslation();

  const addBaudrateMapping = () => {
    const newBaudrate = prompt('Enter baudrate (e.g., 9600):');
    const newValue = prompt('Enter register value for this baudrate:');
    if (newBaudrate && newValue) {
      setBaudrateMappings({
        ...baudrateMappings,
        [newBaudrate]: parseInt(newValue, 10),
      });
    }
  };

  const removeBaudrateMapping = (baudrate: string) => {
    const newMappings = { ...baudrateMappings };
    delete newMappings[baudrate];
    setBaudrateMappings(newMappings);
  };

  return (
    <div className="card bg-base-200">
      <div className="card-body">
        <h3 className="card-title text-lg">{t('modbus_creator.set_base_config')}</h3>
        
        <div className="space-y-4">
          <div className="form-control">
            <label className="label cursor-pointer justify-start gap-2">
              <input
                type="checkbox"
                className="checkbox"
                checked={enableSetAddress}
                onChange={(e) => setEnableSetAddress(e.target.checked)}
              />
              <span className="label-text">{t('modbus_creator.enable_set_address')}</span>
            </label>
            {enableSetAddress && (
              <div className="ml-8 mt-2">
                <label className="label">
                  <span className="label-text">{t('modbus_creator.address_register')}</span>
                </label>
                <NumericInput
                  className="input-sm w-32"
                  value={setAddressAddress}
                  onChange={(v) => setSetAddressAddress(v === '' ? 0 : v)}
                />
              </div>
            )}
          </div>
          
          <div className="form-control">
            <label className="label cursor-pointer justify-start gap-2">
              <input
                type="checkbox"
                className="checkbox"
                checked={enableSetBaudrate}
                onChange={(e) => setEnableSetBaudrate(e.target.checked)}
              />
              <span className="label-text">{t('modbus_creator.enable_set_baudrate')}</span>
            </label>
            {enableSetBaudrate && (
              <div className="ml-8 mt-2 space-y-2">
                <div>
                  <label className="label">
                    <span className="label-text">{t('modbus_creator.baudrate_register')}</span>
                  </label>
                  <NumericInput
                    className="input-sm w-32"
                    value={baudrateAddress}
                    onChange={(v) => setBaudrateAddress(v === '' ? 0 : v)}
                  />
                </div>
                <div>
                  <label className="label">
                    <span className="label-text">{t('modbus_creator.baudrate_mappings')}</span>
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(baudrateMappings).map(([baudrate, value]) => (
                      <div key={baudrate} className="badge badge-outline gap-1">
                        {baudrate}: {value}
                        <button
                          className="btn btn-ghost btn-xs p-0"
                          onClick={() => removeBaudrateMapping(baudrate)}
                        >
                          <FaTimes size={8} />
                        </button>
                      </div>
                    ))}
                    <button className="btn btn-ghost btn-xs" onClick={addBaudrateMapping}>
                      <FaPlus size={10} /> Add
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
