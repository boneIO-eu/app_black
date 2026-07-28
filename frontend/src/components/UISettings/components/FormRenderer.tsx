/**
 * FormRenderer - Renders the appropriate form component based on section type.
 * Extracted from ArrayTableWidget to reduce component size.
 */
import React from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import BinarySensorForm from '../BinarySensorForm';
import EventForm from '../EventForm';
import OutputForm from '../OutputForm';
import OutputGroupForm from '../OutputGroupForm';
import CoverForm from '../CoverForm';
import ModbusDeviceForm from '../ModbusDeviceForm';
import AreasForm from '../AreasForm';
import SensorForm from '../SensorForm';
import VirtualEnergySensorForm from '../VirtualEnergySensorForm';
import RemoteDeviceForm from '../RemoteDeviceForm';
import TemplateForm from '../TemplateForm';
import ADCForm from '../ADCForm';
import BoardSensorsForm from '../BoardSensorsForm';
import DS2482Form from '../DS2482Form';
import RemoteInputForm from '../RemoteInputForm';
import RemoteOutputForm from '../RemoteOutputForm';
import InputTypeSwitcher from './InputTypeSwitcher';

interface FormRendererProps {
  sectionType: string;
  editingItem: any;
  editingIndex: number | null;
  schema: any;
  uiSchema?: any;
  deviceType?: string;
  // Data lists
  allBinarySensors: any[];
  allEvents: any[];
  allOutputs: any[];
  allOutputGroups: any[];
  allCovers: any[];
  allAreas: any[];
  allSensors: any[];
  allModbusDevices: any[];
  allRemoteDevices: any[];
  allRemoteInputs?: any[];
  // Saved snapshots
  savedOutputs?: any[];
  savedOutputGroups?: any[];
  savedCovers?: any[];
  // Section-specific data
  value: any[];
  interlockGroups: string[];
  availableDallasSensors: { address: string; type: string }[];
  // Callbacks
  onChange: (item: any) => void;
  onSave: (e?: any) => void;
  onCancel: () => void;
  onValidationChange: (hasErrors: boolean) => void;
  onInterlockGroupCreated: (name: string) => void;
  attemptedSubmit: boolean;
  /** Optional initial tab for EventForm (e.g., 'single', 'double', 'long'). */
  initialTab?: string;
}

/**
 * Shared props passed to BinarySensorForm and EventForm.
 */
function inputFormProps(props: FormRendererProps) {
  return {
    data: props.editingItem,
    onChange: props.onChange,
    onSave: props.onSave,
    onCancel: props.onCancel,
    isNew: props.editingIndex === null,
    schema: props.schema,
    allBinarySensors: props.allBinarySensors,
    allEvents: props.allEvents,
    allOutputs: props.allOutputs,
    allOutputGroups: props.allOutputGroups,
    allCovers: props.allCovers,
    allAreas: props.allAreas,
    allRemoteDevices: props.allRemoteDevices,
    allRemoteInputs: props.allRemoteInputs || [],
    editingIndex: props.editingIndex,
    onValidationChange: props.onValidationChange,
    attemptedSubmit: props.attemptedSubmit,
    savedOutputs: props.savedOutputs,
    savedOutputGroups: props.savedOutputGroups,
    savedCovers: props.savedCovers,
    initialTab: props.initialTab,
  };
}

/**
 * Renders the correct form for the given section type.
 */
const FormRenderer: React.FC<FormRendererProps> = (props) => {
  const { t } = useTranslation();
  const { sectionType, editingItem, editingIndex, schema, uiSchema, deviceType, value } = props;

  // Merged local inputs — show type switcher + delegate to correct form
  if (sectionType === 'local_inputs') {
    const currentType = editingItem._type === 'binary_sensor' ? 'binary_sensor' : 'event';
    return (
      <div className="space-y-4">
        <InputTypeSwitcher
          currentType={currentType}
          data={editingItem}
          onSwitch={props.onChange}
        />
        {currentType === 'binary_sensor'
          ? <BinarySensorForm {...inputFormProps(props)} />
          : <EventForm {...inputFormProps(props)} />}
      </div>
    );
  }

  // Remote inputs — mode switcher + dedicated form
  if (sectionType === 'remote_inputs') {
    const mode = editingItem.mode === 'event' ? 'event' : 'binary_sensor';
    return (
      <div className="space-y-4">
        {/* Mode selector (binary_sensor or event) */}
        <InputTypeSwitcher
          currentType={mode}
          data={{ ...editingItem, _type: mode }}
          onSwitch={(transformed) => {
            // Map _type back to mode for remote inputs
            const { _type, ...rest } = transformed;
            props.onChange({ ...rest, mode: _type === 'event' ? 'event' : undefined });
          }}
        />
        <RemoteInputForm
          data={editingItem}
          onChange={props.onChange}
          onSave={props.onSave}
          onCancel={props.onCancel}
          isNew={props.editingIndex === null}
          schema={props.schema}
          allOutputs={props.allOutputs}
          allOutputGroups={props.allOutputGroups}
          allCovers={props.allCovers}
          allAreas={props.allAreas}
          allRemoteDevices={props.allRemoteDevices}
          allRemoteInputs={props.allRemoteInputs || []}
          allBinarySensors={props.allBinarySensors}
          onValidationChange={props.onValidationChange}
          attemptedSubmit={props.attemptedSubmit}
          savedOutputs={props.savedOutputs}
          savedOutputGroups={props.savedOutputGroups}
          savedCovers={props.savedCovers}
          initialTab={props.initialTab as any}
        />
      </div>
    );
  }

  // Remote outputs — simple form (no action tabs)
  if (sectionType === 'remote_outputs') {
    return (
      <RemoteOutputForm
        data={editingItem}
        onChange={props.onChange}
        isNew={props.editingIndex === null}
        schema={props.schema}
        allAreas={props.allAreas}
        allRemoteDevices={props.allRemoteDevices}
        existingItems={value}
        editingIndex={editingIndex}
        onValidationChange={props.onValidationChange}
        attemptedSubmit={props.attemptedSubmit}
        interlockGroups={props.interlockGroups}
        onInterlockGroupCreated={props.onInterlockGroupCreated}
      />
    );
  }

  switch (sectionType) {
    case 'binary_sensor':
      return <BinarySensorForm {...inputFormProps(props)} />;

    case 'event':
      return <EventForm {...inputFormProps(props)} />;

    case 'output':
      return (
        <OutputForm
          data={editingItem}
          onChange={props.onChange}
          onSave={props.onSave}
          onCancel={props.onCancel}
          isNew={editingIndex === null}
          schema={schema}
          uiSchema={uiSchema}
          deviceType={deviceType}
          allOutputs={value}
          allAreas={props.allAreas}
          editingIndex={editingIndex}
          interlockGroups={props.interlockGroups}
          onInterlockGroupCreated={props.onInterlockGroupCreated}
          allCovers={props.allCovers}
        />
      );

    case 'output_group':
      return (
        <OutputGroupForm
          data={editingItem}
          onChange={props.onChange}
          schema={schema}
          allOutputs={props.allOutputs}
          allAreas={props.allAreas}
        />
      );

    case 'cover':
      return (
        <CoverForm
          data={editingItem}
          onChange={props.onChange}
          schema={schema}
          allOutputs={props.allOutputs}
          allAreas={props.allAreas}
        />
      );

    case 'modbus_devices':
      return (
        <ModbusDeviceForm
          data={editingItem}
          onChange={props.onChange}
          schema={schema}
          areas={props.allAreas}
        />
      );

    case 'areas':
      return <AreasForm data={editingItem} onChange={props.onChange} />;

    case 'sensor':
      return (
        <SensorForm
          data={editingItem}
          onChange={props.onChange}
          onSave={props.onSave}
          onCancel={props.onCancel}
          isNew={editingIndex === null}
          schema={schema}
          allAreas={props.allAreas}
          availableSensors={props.availableDallasSensors}
          existingSensors={value}
          editingIndex={editingIndex}
          onValidationChange={props.onValidationChange}
        />
      );

    case 'virtual_energy_sensor':
      return (
        <VirtualEnergySensorForm
          data={editingItem}
          onChange={props.onChange}
          onSave={props.onSave}
          onCancel={props.onCancel}
          isNew={editingIndex === null}
          schema={schema}
          allAreas={props.allAreas}
          allOutputs={props.allOutputs}
          existingSensors={value}
          editingIndex={editingIndex}
          onValidationChange={props.onValidationChange}
        />
      );

    case 'remote_devices':
      return <RemoteDeviceForm data={editingItem} onChange={props.onChange} />;

    case 'template':
      return (
        <TemplateForm
          data={editingItem}
          onChange={props.onChange}
          schema={schema}
          allOutputs={props.allOutputs}
          allAreas={props.allAreas}
          allSensors={props.allSensors}
          allModbusDevices={props.allModbusDevices}
          allInputs={props.allBinarySensors || []}
          allRemoteInputs={props.allRemoteInputs || []}
          onValidationChange={props.onValidationChange}
        />
      );

    case 'adc':
      return (
        <ADCForm
          data={editingItem}
          onChange={props.onChange}
          existingItems={value}
          editingIndex={editingIndex}
          allAreas={props.allAreas}
          onValidationChange={props.onValidationChange}
        />
      );

    case 'board_sensors':
      return (
        <BoardSensorsForm
          data={editingItem}
          onChange={props.onChange}
          existingItems={value}
          editingIndex={editingIndex}
          onValidationChange={props.onValidationChange}
        />
      );

    case 'ds2482':
      return (
        <DS2482Form
          data={editingItem}
          onChange={props.onChange}
          onSave={props.onSave}
          onCancel={props.onCancel}
          isNew={editingIndex === null}
          schema={schema}
          existingItems={value}
          editingIndex={editingIndex}
          onValidationChange={props.onValidationChange}
        />
      );

    default:
      return (
        <div className="alert alert-warning">
          <span>{t('array_table_widget.no_form_available').replace('{sectionType}', sectionType)}</span>
        </div>
      );
  }
};

export default FormRenderer;
