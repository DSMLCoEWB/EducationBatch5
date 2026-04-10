import { CategoryInfo } from '../types';

export const categories: CategoryInfo[] = [
  {
    id: 'all',
    label: 'Inbox',
    color: 'text-foreground',
    bgColor: 'bg-muted',
    icon: 'inbox'
  },
  {
    id: 'demo',
    label: 'Demo Emails',
    color: 'text-gov-green',
    bgColor: 'bg-gov-green-light',
    icon: 'star'
  },
  {
    id: 'suspension',
    label: 'Suspension / Disciplinary',
    color: 'text-gov-orange',
    bgColor: 'bg-gov-orange-light',
    icon: 'alert-circle'
  },
  {
    id: 'fir',
    label: 'FIR / Arrest',
    color: 'text-gov-red',
    bgColor: 'bg-gov-red-light',
    icon: 'shield-alert'
  },
  {
    id: 'semester',
    label: 'Semester / Examination',
    color: 'text-primary',
    bgColor: 'bg-gov-blue-light',
    icon: 'graduation-cap'
  },
  {
    id: 'scholarship',
    label: 'Scholarship',
    color: 'text-amber-600',
    bgColor: 'bg-amber-50',
    icon: 'banknote'
  },
  {
    id: 'miscellaneous',
    label: 'Miscellaneous',
    color: 'text-muted-foreground',
    bgColor: 'bg-muted',
    icon: 'folder'
  },
  {
    id: 'Sent',
    label: 'Sent',
    color: 'text-gov-purple',
    bgColor: 'bg-gov-purple-light',
    icon: 'send'
  },
  {
    id: 'trash',
    label: 'Trash',
    color: 'text-gov-red',
    bgColor: 'bg-gov-red-light',
    icon: 'trash'
  }
];

export const getCategoryInfo = (categoryId: string): CategoryInfo => {
  return categories.find(cat => cat.id === categoryId) || categories[0];
};
