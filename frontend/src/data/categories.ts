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
    id: 'Suspension / Disciplinary',
    label: 'Suspension / Disciplinary',
    color: 'text-gov-orange',
    bgColor: 'bg-gov-orange-light',
    icon: 'alert-circle'
  },
  {
    id: 'Legal Issues',
    label: 'Legal Issues',
    color: 'text-gov-red',
    bgColor: 'bg-gov-red-light',
    icon: 'shield-alert'
  },
  {
    id: 'RTI Matters',
    label: 'RTI Matters',
    color: 'text-primary',
    bgColor: 'bg-gov-blue-light',
    icon: 'folder'
  },
  {
    id: 'CMO Issues',
    label: 'CMO Issues',
    color: 'text-gov-red',
    bgColor: 'bg-gov-red-light',
    icon: 'folder'
  },
  {
    id: 'Semester / Examination',
    label: 'Semester / Examination',
    color: 'text-primary',
    bgColor: 'bg-gov-blue-light',
    icon: 'graduation-cap'
  },
  {
    id: 'Scholarship & Fee Concession',
    label: 'Scholarship & Fee Concession',
    color: 'text-gov-green',
    bgColor: 'bg-gov-green-light',
    icon: 'folder'
  },
  {
    id: 'Purchase / Procurement Issues',
    label: 'Purchase / Procurement Issues',
    color: 'text-gov-amber',
    bgColor: 'bg-gov-amber-light',
    icon: 'folder'
  },
  {
    id: 'Cash Issues',
    label: 'Cash Issues',
    color: 'text-gov-red',
    bgColor: 'bg-gov-red-light',
    icon: 'folder'
  },
  {
    id: 'Anti-Ragging Complaints',
    label: 'Anti-Ragging Complaints',
    color: 'text-gov-orange',
    bgColor: 'bg-gov-orange-light',
    icon: 'shield-alert'
  },
  {
    id: 'Accreditation & Ranking',
    label: 'Accreditation & Ranking',
    color: 'text-gov-green',
    bgColor: 'bg-gov-green-light',
    icon: 'folder'
  },
  {
    id: 'Service Matters',
    label: 'Service Matters',
    color: 'text-gov-amber',
    bgColor: 'bg-gov-amber-light',
    icon: 'folder'
  },
  {
    id: 'Appointment Issues',
    label: 'Appointment Issues',
    color: 'text-gov-amber',
    bgColor: 'bg-gov-amber-light',
    icon: 'folder'
  },
  {
    id: 'Transfer Cases',
    label: 'Transfer Cases',
    color: 'text-gov-amber',
    bgColor: 'bg-gov-amber-light',
    icon: 'folder'
  },
  {
    id: 'Inspection Matters',
    label: 'Inspection Matters',
    color: 'text-primary',
    bgColor: 'bg-gov-blue-light',
    icon: 'folder'
  },
  {
    id: 'Seat Matrix Issues',
    label: 'Seat Matrix Issues',
    color: 'text-primary',
    bgColor: 'bg-gov-blue-light',
    icon: 'folder'
  },
  {
    id: 'Miscellaneous',
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
  return categories.find(cat => cat.id === categoryId) || {
    id: categoryId,
    label: categoryId,
    color: 'text-muted-foreground',
    bgColor: 'bg-muted',
    icon: 'folder'
  };
};