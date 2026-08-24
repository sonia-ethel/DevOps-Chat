export interface AWSRegion {
  code: string;
  name: string;
  location: string;
}

export const AWS_REGIONS: AWSRegion[] = [
  // Europe (par défaut eu-west-1)
  { code: 'eu-west-1', name: 'Europe (Ireland)', location: 'Dublin' },
  { code: 'eu-west-2', name: 'Europe (London)', location: 'London' },
  { code: 'eu-west-3', name: 'Europe (Paris)', location: 'Paris' },
  { code: 'eu-central-1', name: 'Europe (Frankfurt)', location: 'Frankfurt' },
  { code: 'eu-north-1', name: 'Europe (Stockholm)', location: 'Stockholm' },
  { code: 'eu-south-1', name: 'Europe (Milan)', location: 'Milan' },
  
  // États-Unis
  { code: 'us-east-1', name: 'US East (N. Virginia)', location: 'N. Virginia' },
  { code: 'us-east-2', name: 'US East (Ohio)', location: 'Ohio' },
  { code: 'us-west-1', name: 'US West (N. California)', location: 'N. California' },
  { code: 'us-west-2', name: 'US West (Oregon)', location: 'Oregon' },
  
  // Asie-Pacifique
  { code: 'ap-southeast-1', name: 'Asia Pacific (Singapore)', location: 'Singapore' },
  { code: 'ap-southeast-2', name: 'Asia Pacific (Sydney)', location: 'Sydney' },
  { code: 'ap-northeast-1', name: 'Asia Pacific (Tokyo)', location: 'Tokyo' },
  { code: 'ap-northeast-2', name: 'Asia Pacific (Seoul)', location: 'Seoul' },
  { code: 'ap-south-1', name: 'Asia Pacific (Mumbai)', location: 'Mumbai' },
  
  // Autres régions
  { code: 'ca-central-1', name: 'Canada (Central)', location: 'Canada' },
  { code: 'sa-east-1', name: 'South America (São Paulo)', location: 'São Paulo' },
];

export const DEFAULT_AWS_REGION = 'eu-west-1';

export function getRegionByCode(code: string): AWSRegion | undefined {
  return AWS_REGIONS.find(region => region.code === code);
}

export function getDefaultRegion(): AWSRegion {
  return getRegionByCode(DEFAULT_AWS_REGION)!;
}