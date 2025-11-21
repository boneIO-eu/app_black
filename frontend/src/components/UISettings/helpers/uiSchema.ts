import { UiSchema } from '@rjsf/utils';

/**
 * Custom UI schema for better form styling
 */
export const getUiSchema = (sectionName: string): UiSchema => {
  const baseUiSchema: UiSchema = {
    'ui:classNames': 'space-y-4',
    'ui:autocomplete': 'off',
    'ui:options': {
      classNames: ''
    },
  };

  // Section-specific UI customizations
  switch (sectionName) {
    case 'boneio':
      return {
        ...baseUiSchema,
        device_type: {
          'ui:widget': 'BoneIOSelectWidget'
        },
        version: {
          'ui:widget': 'BoneIOSelectWidget'
        }
      };
    case 'mqtt':
      return {
        ...baseUiSchema,
        password: {
          'ui:widget': 'password',
          'ui:help': 'MQTT broker password',
          'ui:autocomplete': 'new-password'
        },
        port: {
          'ui:widget': 'updown'
        },
        host: {},
        username: {},
        ha_discovery: {
          'ui:classNames': 'border border-gray-200 rounded-lg p-4 bg-gray-50',
          enabled: {
            'ui:widget': 'CheckboxWidget'
          }
        }
      };
    case 'logger': {
      return {
        ...baseUiSchema,
        levedefault: {
          'ui:widget': 'select'
        }
      }
    };
    case 'web':
      return {
        ...baseUiSchema,
        port: {
          'ui:widget': 'updown'
        },
        auth: {
          password: {
            'ui:widget': 'password',
            'ui:autocomplete': 'new-password'
          }
        }
      };
    case 'cover':
      return {
        ...baseUiSchema,
        'ui:order': ['*'],
        items: {
          restore_state: {
            'ui:widget': 'checkbox',
            'ui:classNames': 'toggle'
          },
          open_time: {
            'ui:widget': 'updown',
            'ui:help': 'Time in milliseconds (e.g., 30000 for 30 seconds)'
          },
          close_time: {
            'ui:widget': 'updown',
            'ui:help': 'Time in milliseconds (e.g., 30000 for 30 seconds)'
          },
          tilt_duration: {
            'ui:widget': 'updown',
            'ui:help': 'Time in milliseconds (e.g., 2000 for 2 seconds)'
          },
          actuator_activation_duration: {
            'ui:widget': 'updown',
            'ui:help': 'Time in milliseconds (e.g., 30000 for 30 seconds)'
          }
        }
      };
    case 'event':
    case 'binary_sensor':
      // Dla tych sekcji używamy custom renderowania w SectionForm
      return {
        "items": {
          ...baseUiSchema,
          "ui:field": "LayoutGridField",
          "ui:layoutGrid": {
            "ui:row": [
              {
                "ui:row": {
                  className: 'grid grid-cols-2 gap-4 col-span-12',
                  children: [
                    {
                      "ui:col": {
                        "children": [
                          "id"
                        ]
                      }
                    },
                    {
                      "ui:col": {
                        "children": [
                          "boneio_output"
                        ]
                      }
                    }
                  ]
                }
              },
              {
                "ui:row": {
                  className: 'grid grid-cols-2 gap-4 col-span-12',
                  children: [

                    {
                      "ui:col": {
                        "children": [
                          "bounce_time"
                        ]
                      }
                    }
                  ]
                }
              },
              {
                "ui:row": {
                  className: 'grid grid-cols-1 gap-4 col-span-12',
                  children: [
                    {
                      "ui:col": {
                        "children": [
                          "show_in_ha"
                        ]
                      }
                    },
                    {
                      "ui:col": {
                        "children": [
                          "inverted"
                        ]
                      }
                    },
                    {
                      "ui:col": {
                        "children": [
                          "clear_message"
                        ]
                      }
                    }
                  ]
                }
              },
              {
                "ui:row": {
                  className: 'grid grid-cols-1 gap-4 col-span-12',
                  children: [

                    {
                      "ui:col": {
                        "className": "actions-grid",
                        "children": [
                          "actions"
                        ]
                      }
                    }
                  ]
                }
              },
            ]
          },
          "gpio_mode": {
            'ui:widget': 'hidden'
          },
          "pin": {
            'ui:widget': 'hidden'
          },
          "detection_type": {
            'ui:widget': 'hidden'
          },
          "show_in_ha": {
            'ui:widget': 'checkbox',
            'ui:classNames': 'toggle'
          },
          "inverted": {
            'ui:widget': 'checkbox',
            'ui:classNames': 'toggle'
          },
          "clear_message": {
            'ui:widget': 'checkbox',
            'ui:classNames': 'toggle'
          },
          "actions": {
            'ui:title': 'Actions Configuration',
            'ui:description': 'Configure actions for pressed and released events',
            'ui:classNames': 'border border-gray-200 rounded-lg p-4 bg-gray-50',
            "pressed": {
              'ui:title': 'Pressed Actions',
              'ui:description': 'Actions to execute when button is pressed',
              'ui:classNames': 'mt-4',
              "items": {
                'ui:classNames': 'border border-blue-200 rounded-md p-3 mb-3 bg-blue-50',
                'ui:title': 'Action',
                "action": {
                  'ui:widget': 'select',
                  'ui:placeholder': 'Select action type'
                },
                "pin": {
                  'ui:widget': 'OutputSelectWidget',
                  'ui:title': 'Output',
                  'ui:placeholder': 'Select output...'
                },
                "topic": {
                  'ui:title': 'MQTT Topic',
                  'ui:placeholder': 'e.g., home/device/command',
                  'ui:help': 'Required for MQTT actions'
                },
                "action_cover": {
                  'ui:widget': 'select',
                  'ui:title': 'Cover Action'
                },
                "data": {
                  'ui:title': 'Additional Data',
                  'ui:widget': 'textarea',
                  'ui:options': {
                    'rows': 3
                  },
                  'ui:help': 'Extra data to send (JSON format for objects)'
                }
              }
            },
            "released": {
              'ui:title': 'Released Actions',
              'ui:description': 'Actions to execute when button is released',
              'ui:classNames': 'mt-4',
              "items": {
                'ui:classNames': 'border border-green-200 rounded-md p-3 mb-3 bg-green-50',
                'ui:title': 'Action',
                "action": {
                  'ui:widget': 'select',
                  'ui:placeholder': 'Select action type'
                },
                "pin": {
                  'ui:widget': 'OutputSelectWidget',
                  'ui:title': 'Output',
                  'ui:placeholder': 'Select output...'
                },
                "topic": {
                  'ui:title': 'MQTT Topic',
                  'ui:placeholder': 'e.g., home/device/command',
                  'ui:help': 'Required for MQTT actions'
                },
                "action_cover": {
                  'ui:widget': 'select',
                  'ui:title': 'Cover Action'
                },
                "data": {
                  'ui:title': 'Additional Data',
                  'ui:widget': 'textarea',
                  'ui:options': {
                    'rows': 3
                  },
                  'ui:help': 'Extra data to send (JSON format for objects)'
                }
              }
            }
          }
        }
      };
      case 'output':
        // Dla tych sekcji używamy custom renderowania w SectionForm
        return {
          "items": {
            ...baseUiSchema,
            "ui:field": "LayoutGridField",
            "ui:layoutGrid": {
              "ui:row": [
                {
                  "ui:row": {
                    className: 'grid grid-cols-2 gap-4 col-span-12',
                    children: [
                      {
                        "ui:col": {
                          "children": [
                            "id"
                          ]
                        }
                      },
                      {
                        "ui:col": {
                          "children": [
                            "boneio_input"
                          ]
                        }
                      }
                    ]
                  }
                },
                {
                  "ui:row": {
                    className: 'grid grid-cols-2 gap-4 col-span-12',
                    children: [
  
                      {
                        "ui:col": {
                          "children": [
                            "bounce_time"
                          ]
                        }
                      }
                    ]
                  }
                },
                {
                  "ui:row": {
                    className: 'grid grid-cols-1 gap-4 col-span-12',
                    children: [
                      {
                        "ui:col": {
                          "children": [
                            "show_in_ha"
                          ]
                        }
                      },
                      {
                        "ui:col": {
                          "children": [
                            "inverted"
                          ]
                        }
                      },
                      {
                        "ui:col": {
                          "children": [
                            "clear_message"
                          ]
                        }
                      }
                    ]
                  }
                },
                {
                  "ui:row": {
                    className: 'grid grid-cols-1 gap-4 col-span-12',
                    children: [
  
                      {
                        "ui:col": {
                          "className": "actions-grid",
                          "children": [
                            "actions"
                          ]
                        }
                      }
                    ]
                  }
                },
              ]
            },
            "gpio_mode": {
              'ui:widget': 'hidden'
            },
            "pin": {
              'ui:widget': 'hidden'
            },
            "detection_type": {
              'ui:widget': 'hidden'
            },
            "show_in_ha": {
              'ui:widget': 'checkbox',
              'ui:classNames': 'toggle'
            },
            "inverted": {
              'ui:widget': 'checkbox',
              'ui:classNames': 'toggle'
            },
            "clear_message": {
              'ui:widget': 'checkbox',
              'ui:classNames': 'toggle'
            },
            "actions": {
              'ui:title': 'Actions Configuration',
              'ui:description': 'Configure actions for pressed and released events',
              'ui:classNames': 'border border-gray-200 rounded-lg p-4 bg-gray-50',
              "pressed": {
                'ui:title': 'Pressed Actions',
                'ui:description': 'Actions to execute when button is pressed',
                'ui:classNames': 'mt-4',
                "items": {
                  'ui:classNames': 'border border-blue-200 rounded-md p-3 mb-3 bg-blue-50',
                  'ui:title': 'Action',
                  "action": {
                    'ui:widget': 'select',
                    'ui:placeholder': 'Select action type'
                  },
                  "pin": {
                    'ui:title': 'Target Pin',
                    'ui:placeholder': 'e.g., Gabinet1'
                  },
                  "topic": {
                    'ui:title': 'MQTT Topic',
                    'ui:placeholder': 'e.g., home/device/command',
                    'ui:help': 'Required for MQTT actions'
                  },
                  "action_cover": {
                    'ui:widget': 'select',
                    'ui:title': 'Cover Action'
                  },
                  "data": {
                    'ui:title': 'Additional Data',
                    'ui:widget': 'textarea',
                    'ui:options': {
                      'rows': 3
                    },
                    'ui:help': 'Extra data to send (JSON format for objects)'
                  }
                }
              },
              "released": {
                'ui:title': 'Released Actions',
                'ui:description': 'Actions to execute when button is released',
                'ui:classNames': 'mt-4',
                "items": {
                  'ui:classNames': 'border border-green-200 rounded-md p-3 mb-3 bg-green-50',
                  'ui:title': 'Action',
                  "action": {
                    'ui:widget': 'select',
                    'ui:placeholder': 'Select action type'
                  },
                  "pin": {
                    'ui:title': 'Target Pin',
                    'ui:placeholder': 'e.g., Gabinet1'
                  },
                  "topic": {
                    'ui:title': 'MQTT Topic',
                    'ui:placeholder': 'e.g., home/device/command',
                    'ui:help': 'Required for MQTT actions'
                  },
                  "action_cover": {
                    'ui:widget': 'select',
                    'ui:title': 'Cover Action'
                  },
                  "data": {
                    'ui:title': 'Additional Data',
                    'ui:widget': 'textarea',
                    'ui:options': {
                      'rows': 3
                    },
                    'ui:help': 'Extra data to send (JSON format for objects)'
                  }
                }
              }
            }
          }
        };
    case 'modbus_devices':
      return {
        ...baseUiSchema,
        items: {
          update_interval: {
            'ui:widget': 'TimePeriodWidget',
            'ui:options': {
              minimum: 1000 // 1 second minimum
            }
          },
          model: {
            'ui:widget': 'SelectWidget',
            'ui:placeholder': 'Select modbus device model'
          },
          address: {
            'ui:help': 'Modbus address of the device'
          },
          id: {
            'ui:help': 'Unique identifier for the device'
          }
        }
      };
    default:
      return {
        ...baseUiSchema,
        'ui:globalOptions': {
          classNames: 'space-y-4'
        }
      };
  }
};