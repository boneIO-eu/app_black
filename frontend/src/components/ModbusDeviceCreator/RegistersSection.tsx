import { useTranslation } from '@/hooks/useTranslation';
import { FaPlus } from 'react-icons/fa';
import { Register, groupRegistersIntoBlocks } from './types';
import RegisterItem from './RegisterItem';

interface RegistersSectionProps {
  registers: Register[];
  testing: string | null;
  onAddRegister: () => void;
  onUpdateRegister: (registerId: string, updates: Partial<Register>) => void;
  onRemoveRegister: (registerId: string) => void;
  onTestRegister: (register: Register) => void;
}

export default function RegistersSection({
  registers,
  testing,
  onAddRegister,
  onUpdateRegister,
  onRemoveRegister,
  onTestRegister,
}: RegistersSectionProps) {
  const { t } = useTranslation();

  const getBlocksInfo = () => {
    const blocks = groupRegistersIntoBlocks(registers);
    return blocks.map(b => `${b.register_type}: base=${b.base}, length=${b.length}`).join(' | ');
  };

  return (
    <div className="card bg-base-200">
      <div className="card-body">
        <div className="flex justify-between items-center">
          <div>
            <h3 className="card-title text-lg">{t('modbus_creator.registers')}</h3>
            {registers.length > 0 && (
              <div className="text-sm text-base-content/70 mt-1">
                {t('modbus_creator.calculated')}: {getBlocksInfo()}
              </div>
            )}
          </div>
          <button className="btn btn-primary btn-sm" onClick={onAddRegister}>
            <FaPlus className="mr-1" /> {t('modbus_creator.add_register')}
          </button>
        </div>
        
        {registers.length === 0 ? (
          <div className="text-base-content/50 text-center py-8">
            {t('modbus_creator.no_registers')}
          </div>
        ) : (
          <div className="space-y-3 mt-4">
            {registers.map((register) => (
              <RegisterItem
                key={register.id}
                register={register}
                testing={testing}
                onUpdate={(updates) => onUpdateRegister(register.id, updates)}
                onRemove={() => onRemoveRegister(register.id)}
                onTest={() => onTestRegister(register)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
