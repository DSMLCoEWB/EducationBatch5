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
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
    icon: 'help-circle'
  },
  {
    id: 'CMO Issues',
    label: 'CMO Issues',
    color: 'text-indigo-600',
    bgColor: 'bg-indigo-50',
    icon: 'landmark'
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
    color: 'text-amber-600',
    bgColor: 'bg-amber-50',
    icon: 'banknote'
  },
  {
    id: 'Purchase / Procurement Issues',
    label: 'Purchase / Procurement Issues',
    color: 'text-emerald-600',
    bgColor: 'bg-emerald-50',
    icon: 'shopping-cart'
  },
  {
    id: 'Cash Issues',
    label: 'Cash Issues',
    color: 'text-rose-600',
    bgColor: 'bg-rose-50',
    icon: 'dollar-sign'
  },
  {
    id: 'Anti-Ragging Complaints',
    label: 'Anti-Ragging Complaints',
    color: 'text-orange-600',
    bgColor: 'bg-orange-50',
    icon: 'users'
  },
  {
    id: 'Accreditation & Ranking',
    label: 'Accreditation & Ranking',
    color: 'text-purple-600',
    bgColor: 'bg-purple-50',
    icon: 'award'
  },
  {
    id: 'Service Matters',
    label: 'Service Matters',
    color: 'text-cyan-600',
    bgColor: 'bg-cyan-50',
    icon: 'briefcase'
  },
  {
    id: 'Appointment Issues',
    label: 'Appointment Issues',
    color: 'text-teal-600',
    bgColor: 'bg-teal-50',
    icon: 'user-plus'
  },
  {
    id: 'Transfer Cases',
    label: 'Transfer Cases',
    color: 'text-sky-600',
    bgColor: 'bg-sky-50',
    icon: 'arrow-left-right'
  },
  {
    id: 'Inspection Matters',
    label: 'Inspection Matters',
    color: 'text-violet-600',
    bgColor: 'bg-violet-50',
    icon: 'clipboard-check'
  },
  {
    id: 'Seat Matrix Issues',
    label: 'Seat Matrix Issues',
    color: 'text-fuchsia-600',
    bgColor: 'bg-fuchsia-50',
    icon: 'table'
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
  return categories.find(cat => cat.id === categoryId) || categories[0];
};
