// src/utils/deploymentSteps.ts

import {
  Settings as SettingsIcon,
  Description as PlanIcon,
  Build as ValidationIcon,
  Computer as ComputerIcon,
  Security as SecurityIcon,
  NetworkCheck as NetworkIcon,
  Storage as StorageIcon,
  CheckCircle as CheckCircleIcon
} from '@mui/icons-material';

export interface DeploymentStep {
  id: string;
  label: string;
  description: string;
  progressRange: [number, number]; // [min, max] percentage
  icon: any;
  estimatedDuration?: string;
}

// Étapes détaillées pour le déploiement AWS
export const AWS_DEPLOYMENT_STEPS: DeploymentStep[] = [
  {
    id: 'initialization',
    label: 'Initialisation',
    description: 'Configuration de l\'environnement et validation des paramètres',
    progressRange: [0, 10],
    icon: SettingsIcon,
    estimatedDuration: '10-15s'
  },
  {
    id: 'validation',
    label: 'Validation Terraform',
    description: 'Vérification de la syntaxe et des configurations',
    progressRange: [10, 20],
    icon: ValidationIcon,
    estimatedDuration: '15-20s'
  },
  {
    id: 'planning',
    label: 'Planification',
    description: 'Analyse des ressources à créer et des dépendances',
    progressRange: [20, 30],
    icon: PlanIcon,
    estimatedDuration: '20-30s'
  },
  {
    id: 'networking',
    label: 'Configuration Réseau',
    description: 'Création du VPC, subnets et tables de routage',
    progressRange: [30, 50],
    icon: NetworkIcon,
    estimatedDuration: '30-45s'
  },
  {
    id: 'security_groups',
    label: 'Groupes de Sécurité',
    description: 'Configuration des règles de firewall',
    progressRange: [50, 60],
    icon: SecurityIcon,
    estimatedDuration: '15-20s'
  },
  {
    id: 'compute',
    label: 'Instance EC2',
    description: 'Lancement et configuration de l\'instance',
    progressRange: [60, 80],
    icon: ComputerIcon,
    estimatedDuration: '45-60s'
  },
  {
    id: 'storage',
    label: 'Configuration Stockage',
    description: 'Attachment des volumes EBS',
    progressRange: [80, 90],
    icon: StorageIcon,
    estimatedDuration: '15-20s'
  },
  {
    id: 'finalization',
    label: 'Finalisation',
    description: 'Récupération des outputs et vérifications finales',
    progressRange: [90, 100],
    icon: CheckCircleIcon,
    estimatedDuration: '10-15s'
  }
];

// Fonction pour trouver l'étape courante basée sur le pourcentage
export const getCurrentStep = (progressPercentage: number): DeploymentStep | null => {
  return AWS_DEPLOYMENT_STEPS.find(step => 
    progressPercentage >= step.progressRange[0] && progressPercentage <= step.progressRange[1]
  ) || null;
};

// Fonction pour obtenir l'index de l'étape courante
export const getCurrentStepIndex = (progressPercentage: number): number => {
  const currentStep = getCurrentStep(progressPercentage);
  if (!currentStep) return 0;
  return AWS_DEPLOYMENT_STEPS.findIndex(step => step.id === currentStep.id);
};

// Fonction pour obtenir la description détaillée d'une étape
export const getStepDescription = (stepId: string): string => {
  const step = AWS_DEPLOYMENT_STEPS.find(s => s.id === stepId);
  return step?.description || 'Traitement en cours...';
};

// Fonction pour mapper les messages backend aux étapes
export const mapBackendMessageToStep = (message: string, currentStep: string): DeploymentStep | null => {
  const lowerMessage = (message + ' ' + currentStep).toLowerCase();
  
  if (lowerMessage.includes('init') || lowerMessage.includes('initialisation')) {
    return AWS_DEPLOYMENT_STEPS.find(s => s.id === 'initialization') || null;
  }
  if (lowerMessage.includes('validation') || lowerMessage.includes('validate')) {
    return AWS_DEPLOYMENT_STEPS.find(s => s.id === 'validation') || null;
  }
  if (lowerMessage.includes('plan') || lowerMessage.includes('planification')) {
    return AWS_DEPLOYMENT_STEPS.find(s => s.id === 'planning') || null;
  }
  if (lowerMessage.includes('vpc') || lowerMessage.includes('network') || lowerMessage.includes('réseau')) {
    return AWS_DEPLOYMENT_STEPS.find(s => s.id === 'networking') || null;
  }
  if (lowerMessage.includes('security') || lowerMessage.includes('sécurité') || lowerMessage.includes('firewall')) {
    return AWS_DEPLOYMENT_STEPS.find(s => s.id === 'security_groups') || null;
  }
  if (lowerMessage.includes('ec2') || lowerMessage.includes('instance') || lowerMessage.includes('compute')) {
    return AWS_DEPLOYMENT_STEPS.find(s => s.id === 'compute') || null;
  }
  if (lowerMessage.includes('storage') || lowerMessage.includes('ebs') || lowerMessage.includes('volume')) {
    return AWS_DEPLOYMENT_STEPS.find(s => s.id === 'storage') || null;
  }
  if (lowerMessage.includes('output') || lowerMessage.includes('final') || lowerMessage.includes('completion')) {
    return AWS_DEPLOYMENT_STEPS.find(s => s.id === 'finalization') || null;
  }
  
  return null;
};

// Fonction pour calculer le pourcentage d'avancement dans une étape spécifique
export const getStepProgress = (progressPercentage: number, step: DeploymentStep): number => {
  const [min, max] = step.progressRange;
  if (progressPercentage <= min) return 0;
  if (progressPercentage >= max) return 100;
  return ((progressPercentage - min) / (max - min)) * 100;
};