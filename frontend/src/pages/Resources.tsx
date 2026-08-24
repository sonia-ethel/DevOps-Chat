import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Typography,
  GridLegacy,
  Card,
  CardContent,
  Button,
  Chip,
  IconButton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  Stack,
  Avatar,
  Switch,
  FormControlLabel,
  alpha,
} from '@mui/material';
import {
  CloudQueue,
  Storage,
  PlayArrow,
  Stop,
  Delete,
  Refresh,
  FilterList,
  Search,
  Visibility,
  MoreVert,
  CheckCircle,
  Error,
  Warning,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import axiosClient from '../api/axiosClient';

interface Resource {
  instance_id: string;
  public_ip?: string;
  private_ip?: string;
  state?: string;
  provider: string;
  source: string;
  project_name?: string;
  project_id?: number;
  launch_time?: string;
}

interface ResourceSummary {
  totalInstances: number;
  runningInstances: number;
  stoppedInstances: number;
  providers: { [key: string]: number };
  projects: { [key: string]: number };
  estimatedMonthlyCost: number;
}

const Resources: React.FC = () => {
  // const theme = useTheme();
  const navigate = useNavigate();
  
  const [resources, setResources] = useState<Resource[]>([]);
  const [filteredResources, setFilteredResources] = useState<Resource[]>([]);
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<ResourceSummary | null>(null);
  
  // Filters
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [providerFilter, setProviderFilter] = useState('all');
  const [projectFilter, setProjectFilter] = useState('all');
  const [showOnlyRunning, setShowOnlyRunning] = useState(false);

  useEffect(() => {
    loadResources();
  }, []);

  useEffect(() => {
    applyFilters();
  }, [resources, searchTerm, statusFilter, providerFilter, projectFilter, showOnlyRunning]);

  const loadResources = async () => {
    try {
      setLoading(true);
      
      // Charger toutes les sessions pour avoir les noms de projets
      const sessionsResponse = await axiosClient.get('/sessions/list');
      const sessions = sessionsResponse.data;
      
      // Charger les ressources pour chaque session
      const allResources: Resource[] = [];
      
      for (const session of sessions.slice(0, 3)) { // Limiter pour éviter trop d'appels
        try {
          const resourcesResponse = await axiosClient.get('/resources/list_all_resources', {
            params: { session_id: session.id }
          });
          
          const { cloud_resources = [], database_resources = [] } = resourcesResponse.data;
          const sessionResources = [...cloud_resources, ...database_resources];
          
          // Enrichir avec les infos de projet
          sessionResources.forEach((resource: any) => {
            allResources.push({
              instance_id: resource.instance_id,
              public_ip: resource.public_ip,
              private_ip: resource.private_ip,
              state: resource.state || 'unknown',
              provider: resource.provider || 'aws',
              source: resource.source || 'cloud_api',
              project_name: session.description || `Projet ${session.id}`,
              project_id: session.id,
              launch_time: resource.launch_time,
            });
          });
        } catch (error) {
          console.warn(`Erreur chargement ressources session ${session.id}:`, error);
        }
      }
      
      setResources(allResources);
      
      // Calculer le résumé
      const runningCount = allResources.filter(r => r.state === 'running').length;
      const stoppedCount = allResources.filter(r => r.state === 'stopped').length;
      
      const providerCounts = allResources.reduce((acc, resource) => {
        acc[resource.provider] = (acc[resource.provider] || 0) + 1;
        return acc;
      }, {} as { [key: string]: number });
      
      const projectCounts = allResources.reduce((acc, resource) => {
        const projectName = resource.project_name || 'Projet inconnu';
        acc[projectName] = (acc[projectName] || 0) + 1;
        return acc;
      }, {} as { [key: string]: number });
      
      setSummary({
        totalInstances: allResources.length,
        runningInstances: runningCount,
        stoppedInstances: stoppedCount,
        providers: providerCounts,
        projects: projectCounts,
        estimatedMonthlyCost: allResources.length * 15, // Estimation basique
      });
      
    } catch (error) {
      console.error('Erreur chargement ressources:', error);
    } finally {
      setLoading(false);
    }
  };

  const applyFilters = () => {
    let filtered = resources;

    // Filtre de recherche
    if (searchTerm) {
      filtered = filtered.filter(resource => 
        resource.instance_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
        resource.project_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        resource.public_ip?.includes(searchTerm) ||
        resource.private_ip?.includes(searchTerm)
      );
    }

    // Filtre par statut
    if (statusFilter !== 'all') {
      filtered = filtered.filter(resource => resource.state === statusFilter);
    }

    // Filtre par provider
    if (providerFilter !== 'all') {
      filtered = filtered.filter(resource => resource.provider === providerFilter);
    }

    // Filtre par projet
    if (projectFilter !== 'all') {
      filtered = filtered.filter(resource => resource.project_name === projectFilter);
    }

    // Afficher seulement celles en marche
    if (showOnlyRunning) {
      filtered = filtered.filter(resource => resource.state === 'running');
    }

    setFilteredResources(filtered);
  };

  const getStatusIcon = (state: string) => {
    switch (state) {
      case 'running':
        return <CheckCircle color="success" />;
      case 'stopped':
        return <Stop color="disabled" />;
      case 'pending':
        return <Warning color="warning" />;
      default:
        return <Error color="error" />;
    }
  };

  const getStatusColor = (state: string) => {
    switch (state) {
      case 'running':
        return 'success';
      case 'stopped':
        return 'default';
      case 'pending':
        return 'warning';
      default:
        return 'error';
    }
  };

  const getProviderIcon = () => {
    return <CloudQueue />;
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString();
  };

  const uniqueProviders = Array.from(new Set(resources.map(r => r.provider)));
  const uniqueProjects = Array.from(new Set(resources.map(r => r.project_name).filter(Boolean)));

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4 }}>
        <Box>
          <Typography variant="h4" gutterBottom fontWeight={700}>
            Toutes les Ressources
          </Typography>
          <Typography variant="h6" color="text.secondary">
            Vue d'ensemble de votre infrastructure multi-projets
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<Refresh />}
          onClick={loadResources}
        >
          Actualiser
        </Button>
      </Box>

      {/* Summary Cards */}
      {summary && (
        <GridLegacy container spacing={3} sx={{ mb: 4 }}>
          <GridLegacy item xs={12} sm={6} md={3}>
            <Card sx={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', color: 'white' }}>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  <Avatar sx={{ bgcolor: alpha('#fff', 0.2), mr: 2 }}>
                    <Storage />
                  </Avatar>
                  <Box>
                    <Typography variant="h4" fontWeight={700}>
                      {summary.totalInstances}
                    </Typography>
                    <Typography variant="body2" sx={{ opacity: 0.9 }}>
                      Instances Totales
                    </Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </GridLegacy>

          <GridLegacy item xs={12} sm={6} md={3}>
            <Card sx={{ background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)', color: 'white' }}>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  <Avatar sx={{ bgcolor: alpha('#fff', 0.2), mr: 2 }}>
                    <CheckCircle />
                  </Avatar>
                  <Box>
                    <Typography variant="h4" fontWeight={700}>
                      {summary.runningInstances}
                    </Typography>
                    <Typography variant="body2" sx={{ opacity: 0.9 }}>
                      En Fonctionnement
                    </Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </GridLegacy>

          <GridLegacy item xs={12} sm={6} md={3}>
            <Card sx={{ background: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)', color: 'white' }}>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  <Avatar sx={{ bgcolor: alpha('#fff', 0.2), mr: 2 }}>
                    <CloudQueue />
                  </Avatar>
                  <Box>
                    <Typography variant="h4" fontWeight={700}>
                      {Object.keys(summary.providers).length}
                    </Typography>
                    <Typography variant="body2" sx={{ opacity: 0.9 }}>
                      Providers
                    </Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </GridLegacy>

          <GridLegacy item xs={12} sm={6} md={3}>
            <Card sx={{ background: 'linear-gradient(135deg, #fa709a 0%, #fee140 100%)', color: 'white' }}>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  <Avatar sx={{ bgcolor: alpha('#fff', 0.2), mr: 2 }}>
                    <Storage />
                  </Avatar>
                  <Box>
                    <Typography variant="h4" fontWeight={700}>
                      ~{summary.estimatedMonthlyCost}€
                    </Typography>
                    <Typography variant="body2" sx={{ opacity: 0.9 }}>
                      Coût Mensuel
                    </Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </GridLegacy>
        </GridLegacy>
      )}

      {/* Filters */}
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
            <FilterList sx={{ mr: 1 }} />
            <Typography variant="h6" fontWeight={600}>
              Filtres
            </Typography>
          </Box>
          
          <GridLegacy container spacing={2} alignItems="center">
            <GridLegacy item xs={12} sm={6} md={3}>
              <TextField
                fullWidth
                size="small"
                placeholder="Rechercher..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                InputProps={{
                  startAdornment: <Search sx={{ mr: 1, color: 'text.secondary' }} />,
                }}
              />
            </GridLegacy>
            
            <GridLegacy item xs={12} sm={6} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Statut</InputLabel>
                <Select
                  value={statusFilter}
                  label="Statut"
                  onChange={(e) => setStatusFilter(e.target.value)}
                >
                  <MenuItem value="all">Tous</MenuItem>
                  <MenuItem value="running">En marche</MenuItem>
                  <MenuItem value="stopped">Arrêtées</MenuItem>
                  <MenuItem value="pending">En attente</MenuItem>
                </Select>
              </FormControl>
            </GridLegacy>
            
            <GridLegacy item xs={12} sm={6} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Provider</InputLabel>
                <Select
                  value={providerFilter}
                  label="Provider"
                  onChange={(e) => setProviderFilter(e.target.value)}
                >
                  <MenuItem value="all">Tous</MenuItem>
                  {uniqueProviders.map(provider => (
                    <MenuItem key={provider} value={provider}>
                      {provider.toUpperCase()}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </GridLegacy>
            
            <GridLegacy item xs={12} sm={6} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Projet</InputLabel>
                <Select
                  value={projectFilter}
                  label="Projet"
                  onChange={(e) => setProjectFilter(e.target.value)}
                >
                  <MenuItem value="all">Tous</MenuItem>
                  {uniqueProjects.map(project => (
                    <MenuItem key={project} value={project}>
                      {project}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </GridLegacy>
            
            <GridLegacy item xs={12} sm={6} md={3}>
              <FormControlLabel
                control={
                  <Switch
                    checked={showOnlyRunning}
                    onChange={(e) => setShowOnlyRunning(e.target.checked)}
                  />
                }
                label="Seulement actives"
              />
            </GridLegacy>
          </GridLegacy>
        </CardContent>
      </Card>

      {/* Resources Table */}
      <Card>
        <CardContent>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
            <Typography variant="h6" fontWeight={600}>
              Instances ({filteredResources.length})
            </Typography>
            <Stack direction="row" spacing={1}>
              <Button size="small" startIcon={<PlayArrow />} color="success">
                Démarrer Sélection
              </Button>
              <Button size="small" startIcon={<Stop />} color="warning">
                Arrêter Sélection
              </Button>
              <Button size="small" startIcon={<Delete />} color="error">
                Supprimer Sélection
              </Button>
            </Stack>
          </Box>
          
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Instance</TableCell>
                  <TableCell>Projet</TableCell>
                  <TableCell>Statut</TableCell>
                  <TableCell>Provider</TableCell>
                  <TableCell>IP Publique</TableCell>
                  <TableCell>IP Privée</TableCell>
                  <TableCell>Créée le</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filteredResources.map((resource) => (
                  <TableRow key={resource.instance_id} hover>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        {getStatusIcon(resource.state || 'unknown')}
                        <Typography variant="body2" sx={{ ml: 1, fontFamily: 'monospace' }}>
                          {resource.instance_id}
                        </Typography>
                      </Box>
                    </TableCell>
                    
                    <TableCell>
                      <Button
                        size="small"
                        variant="text"
                        onClick={() => navigate("/chat")}
                      >
                        {resource.project_name}
                      </Button>
                    </TableCell>
                    
                    <TableCell>
                      <Chip
                        label={resource.state}
                        size="small"
                        color={getStatusColor(resource.state || 'unknown') as any}
                        sx={{ textTransform: 'capitalize' }}
                      />
                    </TableCell>
                    
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        <Avatar sx={{ width: 24, height: 24, mr: 1 }}>
                          {getProviderIcon()}
                        </Avatar>
                        <Typography variant="body2">
                          {resource.provider.toUpperCase()}
                        </Typography>
                      </Box>
                    </TableCell>
                    
                    <TableCell>
                      <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                        {resource.public_ip || 'N/A'}
                      </Typography>
                    </TableCell>
                    
                    <TableCell>
                      <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                        {resource.private_ip || 'N/A'}
                      </Typography>
                    </TableCell>
                    
                    <TableCell>
                      <Typography variant="body2">
                        {formatDate(resource.launch_time)}
                      </Typography>
                    </TableCell>
                    
                    <TableCell>
                      <Stack direction="row" spacing={1}>
                        <IconButton
                          size="small"
                          onClick={() => navigate("/chat")}
                        >
                          <Visibility />
                        </IconButton>
                        <IconButton
                          size="small"
                          color={resource.state === 'running' ? 'error' : 'success'}
                        >
                          {resource.state === 'running' ? <Stop /> : <PlayArrow />}
                        </IconButton>
                        <IconButton size="small">
                          <MoreVert />
                        </IconButton>
                      </Stack>
                    </TableCell>
                  </TableRow>
                ))}
                
                {filteredResources.length === 0 && !loading && (
                  <TableRow>
                    <TableCell colSpan={8} sx={{ textAlign: 'center', py: 4 }}>
                      <Typography variant="h6" color="text.secondary" gutterBottom>
                        Aucune ressource trouvée
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Ajustez vos filtres ou créez votre premier projet
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>
    </Container>
  );
};

export default Resources;
