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
import RemoteInputForm from '../RemoteInputForm';
import RemoteOutputForm from '../RemoteOutputForm';
import VirtualSwitchForm from '../VirtualSwitchForm';
import ScheduleForm from '../ScheduleForm';
import InputTypeSwitcher from './InputTypeSwitcher';
import { pickInputVariantSchema } from '../helpers/inputSchema';
import type {
  AreaEntity,
  BinarySensorEntity,
  CoverEntity,
  EventEntity,
  OutputEntity,
  RemoteDeviceEntity,
} from '@/types/config';
import type { ConfigRecord, JsonSchema } from '@/types/jsonSchema';
import type { OutputGroupRecord } from '../ActionFields/types';

/**
 * The item is held here as a ConfigRecord; each form types it (and so its
 * `onChange`) as its own data shape, so those props are cast per form.
 */
type PropsOf<C> = C extends React.ComponentType<infer P> ? P : never;

/** BoardSensorsForm's item has required fields and no index signature, so it
 *  neither accepts a ConfigRecord nor passes as one; it is cast through
 *  `ConfigRecord &` (and its `onChange` as taking any object). */
type BoardSensorData = PropsOf<typeof BoardSensorsForm>['data'];

interface FormRendererProps {
  sectionType: string;
  editingItem: ConfigRecord;
  editingIndex: number | null;
  schema: JsonSchema;
  uiSchema?: ConfigRecord;
  deviceType?: string;
  // Data lists
  allBinarySensors: BinarySensorEntity[];
  allEvents: EventEntity[];
  allOutputs: OutputEntity[];
  allOutputGroups: OutputGroupRecord[];
  allCovers: CoverEntity[];
  allAreas: AreaEntity[];
  allSensors: ConfigRecord[];
  allModbusDevices: ConfigRecord[];
  allRemoteDevices: RemoteDeviceEntity[];
  allRemoteInputs?: ConfigRecord[];
  allVirtualSwitches?: ConfigRecord[];
  // Saved snapshots
  savedOutputs?: OutputEntity[];
  savedOutputGroups?: OutputGroupRecord[];
  savedCovers?: CoverEntity[];
  // Section-specific data
  value: ConfigRecord[];
  interlockGroups: string[];
  availableDallasSensors: { address: string; type: string }[];
  // Callbacks
  onChange: (item: ConfigRecord) => void;
  onSave: () => void;
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
    allVirtualSwitches: props.allVirtualSwitches || [],
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
    // local_inputs carries both item schemas — hand each form the one for its own
    // type, otherwise the binary sensor would be offered the event device classes
    // (button/doorbell/motion) and the event action types.
    const formProps = {
      ...inputFormProps(props),
      schema: pickInputVariantSchema(schema, currentType),
    };
    return (
      <div className="space-y-4">
        <InputTypeSwitcher
          currentType={currentType}
          data={editingItem}
          onSwitch={props.onChange}
        />
        {currentType === 'binary_sensor'
          ? <BinarySensorForm {...formProps} onChange={props.onChange as PropsOf<typeof BinarySensorForm>['onChange']} />
          : <EventForm {...formProps} onChange={props.onChange as PropsOf<typeof EventForm>['onChange']} />}
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
          onChange={props.onChange as PropsOf<typeof RemoteInputForm>['onChange']}
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
          allVirtualSwitches={props.allVirtualSwitches || []}
          allBinarySensors={props.allBinarySensors}
          onValidationChange={props.onValidationChange}
          attemptedSubmit={props.attemptedSubmit}
          savedOutputs={props.savedOutputs}
          savedOutputGroups={props.savedOutputGroups}
          savedCovers={props.savedCovers}
          initialTab={props.initialTab as PropsOf<typeof RemoteInputForm>['initialTab']}
        />
      </div>
    );
  }

  // Remote outputs — simple form (no action tabs)
  if (sectionType === 'remote_outputs') {
    return (
      <RemoteOutputForm
        data={editingItem}
        onChange={props.onChange as PropsOf<typeof RemoteOutputForm>['onChange']}
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
      return <BinarySensorForm {...inputFormProps(props)} onChange={props.onChange as PropsOf<typeof BinarySensorForm>['onChange']} />;

    case 'event':
      return <EventForm {...inputFormProps(props)} onChange={props.onChange as PropsOf<typeof EventForm>['onChange']} />;

    case 'output':
      return (
        <OutputForm
          data={editingItem}
          onChange={props.onChange}
          onSave={props.onSave}
          onCancel={props.onCancel}
          isNew={editingIndex === null}
          schema={schema}
          uiSchema={uiSchema as PropsOf<typeof OutputForm>['uiSchema']}
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
          onChange={props.onChange as PropsOf<typeof CoverForm>['onChange']}
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
          onChange={props.onChange as PropsOf<typeof SensorForm>['onChange']}
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
          onChange={props.onChange as PropsOf<typeof VirtualEnergySensorForm>['onChange']}
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
          onChange={props.onChange as PropsOf<typeof ADCForm>['onChange']}
          existingItems={value}
          editingIndex={editingIndex}
          allAreas={props.allAreas}
          onValidationChange={props.onValidationChange}
        />
      );

    case 'virtual_switch':
      return (
        <VirtualSwitchForm
          data={editingItem as PropsOf<typeof VirtualSwitchForm>['data']}
          onChange={props.onChange}
          allOutputs={props.allOutputs}
          allOutputGroups={props.allOutputGroups}
          allCovers={props.allCovers}
          allAreas={props.allAreas}
          allRemoteDevices={props.allRemoteDevices}
          allBinarySensors={props.allBinarySensors}
          allRemoteInputs={props.allRemoteInputs || []}
          allVirtualSwitches={props.allVirtualSwitches || []}
          savedOutputs={props.savedOutputs}
          savedOutputGroups={props.savedOutputGroups}
          savedCovers={props.savedCovers}
          existingItems={value as PropsOf<typeof VirtualSwitchForm>['existingItems']}
          editingIndex={editingIndex}
          onValidationChange={props.onValidationChange}
          attemptedSubmit={props.attemptedSubmit}
        />
      );

    case 'schedule':
      return (
        <ScheduleForm
          data={editingItem as PropsOf<typeof ScheduleForm>['data']}
          onChange={props.onChange}
          allOutputs={props.allOutputs}
          allOutputGroups={props.allOutputGroups}
          allCovers={props.allCovers}
          allAreas={props.allAreas}
          allRemoteDevices={props.allRemoteDevices}
          allBinarySensors={props.allBinarySensors}
          allRemoteInputs={props.allRemoteInputs || []}
          allVirtualSwitches={props.allVirtualSwitches || []}
          savedOutputs={props.savedOutputs}
          savedOutputGroups={props.savedOutputGroups}
          savedCovers={props.savedCovers}
          existingItems={value as PropsOf<typeof ScheduleForm>['existingItems']}
          editingIndex={editingIndex}
          onValidationChange={props.onValidationChange}
          attemptedSubmit={props.attemptedSubmit}
        />
      );

    case 'board_sensors':
      return (
        <BoardSensorsForm
          data={editingItem as ConfigRecord & BoardSensorData}
          onChange={props.onChange as (data: object) => void}
          existingItems={value as (ConfigRecord & BoardSensorData)[]}
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
