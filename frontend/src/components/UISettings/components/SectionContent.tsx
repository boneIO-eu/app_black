/**
 * SectionContent - Renders the appropriate form/widget for a configuration section.
 * Handles both array sections (ArrayTableWidget) and custom form sections.
 */
import { useTranslation } from '@/hooks/useTranslation';
import ArrayTableWidget from '../ArrayTableWidget';
import BoneIOForm from '../BoneIOForm';
import MqttForm from '../MqttForm';
import WebServerForm from '../WebServerForm';
import ModbusForm from '../ModbusForm';
import CANForm from '../CANForm';
import LoggerForm from '../LoggerForm';
import Mcp23017Form from '../Mcp23017Form';
import { ARRAY_SECTIONS, type ArraySectionType } from '../constants/sectionDefinitions';
import { normalizeCovers } from '../helpers/coverUtils';

interface ConfigSection {
  name: string;
  schema: any;
  normalizedSchema: any;
  uiSchema: any;
  data: Record<string, any>;
}

interface SectionContentProps {
  activeSection: string;
  activeSectionData: ConfigSection;
  formData: Record<string, any>;
  originalData: Record<string, any>;
  schemaLoaded: boolean;
  editItemName?: string;
  onEditItemOpened?: () => void;
  onSectionChange: (sectionName: string, data: any) => void;
  onSaveSection: (sectionName: string, data?: any) => Promise<void>;
}

/**
 * Check if a section is an array section that uses ArrayTableWidget.
 */
function isArraySection(sectionName: string): sectionName is ArraySectionType {
  return ARRAY_SECTIONS.includes(sectionName as ArraySectionType);
}

/**
 * Renders a loading spinner while schema is loading.
 */
function LoadingSpinner({ message }: { message: string }) {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="flex flex-col items-center gap-4">
        <span className="loading loading-spinner loading-lg text-primary"></span>
        <p className="text-base-content/70">{message}</p>
      </div>
    </div>
  );
}

/**
 * Renders ArrayTableWidget with all required props.
 */
function ArraySectionContent({
  activeSection,
  activeSectionData,
  formData,
  originalData,
  editItemName,
  onEditItemOpened,
  onSectionChange,
  onSaveSection,
}: Omit<SectionContentProps, 'schemaLoaded'>) {
  const { t } = useTranslation();
  
  return (
    <ArrayTableWidget
      value={formData[activeSection] || []}
      uiSchema={activeSectionData.uiSchema.items}
      onChange={(newData) => onSectionChange(activeSection, newData)}
      schema={activeSectionData.normalizedSchema}
      sectionType={activeSection as 'binary_sensor' | 'event' | 'output' | 'output_group' | 'cover' | 'modbus_devices' | 'areas' | 'sensor' | 'virtual_energy_sensor' | 'remote_devices' | 'template' | 'other'}
      deviceType={formData.boneio?.device_type}
      allBinarySensors={formData.binary_sensor || []}
      allEvents={formData.event || []}
      allOutputs={formData.output || []}
      allOutputGroups={formData.output_group || []}
      allCovers={formData.cover || []}
      allAreas={formData.areas || []}
      allSensors={[
        ...(formData.sensor || []),
        ...(formData.lm75 || []).map((s: any) => ({ ...s, _source: 'lm75' })),
        ...(formData.mcp9808 || []).map((s: any) => ({ ...s, _source: 'mcp9808' })),
      ]}
      allModbusDevices={formData.modbus_devices || []}
      allVirtualEnergySensors={formData.virtual_energy_sensor || []}
      allRemoteDevices={formData.remote_devices || []}
      savedOutputs={originalData.output || []}
      savedOutputGroups={originalData.output_group || []}
      savedCovers={normalizeCovers(originalData.cover || [])}
      onUpdateEvents={(newEvents) => onSectionChange('event', newEvents)}
      onUpdateBinarySensors={(newSensors) => onSectionChange('binary_sensor', newSensors)}
      onSaveSection={onSaveSection}
      editItemName={editItemName}
      onEditItemOpened={onEditItemOpened}
      title={t(`sections.${activeSection}`)}
    />
  );
}

/**
 * Renders custom form for non-array sections.
 */
function CustomFormContent({
  activeSection,
  formData,
  onSectionChange,
}: Pick<SectionContentProps, 'activeSection' | 'formData' | 'onSectionChange'>) {
  const handleChange = (data: any) => onSectionChange(activeSection, data);
  
  switch (activeSection) {
    case 'boneio':
      return (
        <BoneIOForm
          data={formData[activeSection]}
          onChange={handleChange}
        />
      );
    case 'mqtt':
      return (
        <MqttForm
          data={formData[activeSection]}
          onChange={handleChange}
        />
      );
    case 'web':
      return (
        <WebServerForm
          data={formData[activeSection]}
          onChange={handleChange}
        />
      );
    case 'modbus':
      return (
        <ModbusForm
          data={formData[activeSection]}
          onChange={handleChange}
        />
      );
    case 'can':
      return (
        <CANForm
          data={formData[activeSection]}
          onChange={handleChange}
        />
      );
    case 'logger':
      return (
        <LoggerForm
          data={formData[activeSection]}
          onChange={handleChange}
        />
      );
    case 'mcp23017':
      return (
        <Mcp23017Form
          data={formData[activeSection] || []}
          onChange={handleChange}
        />
      );
    default:
      return (
        <div className="alert alert-warning">
          <span>No form available for section: {activeSection}</span>
        </div>
      );
  }
}

/**
 * Main SectionContent component.
 * Renders the appropriate content based on section type.
 */
export default function SectionContent({
  activeSection,
  activeSectionData,
  formData,
  originalData,
  schemaLoaded,
  editItemName,
  onEditItemOpened,
  onSectionChange,
  onSaveSection,
}: SectionContentProps) {
  const { t } = useTranslation();
  
  if (isArraySection(activeSection)) {
    // Array sections - wait for schema to load
    if (!schemaLoaded) {
      return <LoadingSpinner message={t('settings.loading_schema')} />;
    }
    
    return (
      <ArraySectionContent
        activeSection={activeSection}
        activeSectionData={activeSectionData}
        formData={formData}
        originalData={originalData}
        editItemName={editItemName}
        onEditItemOpened={onEditItemOpened}
        onSectionChange={onSectionChange}
        onSaveSection={onSaveSection}
      />
    );
  }
  
  // Custom form sections
  return (
    <CustomFormContent
      activeSection={activeSection}
      formData={formData}
      onSectionChange={onSectionChange}
    />
  );
}
