import React, { useEffect, useState } from "react";
import {
  Box,
  Container,
  Card,
  CardContent,
  Typography,
  Button,
  Chip,
  Avatar,
  LinearProgress,
  IconButton,
  Stack,
  alpha,
  useTheme,
  Skeleton,
} from "@mui/material";
import {
  CloudQueue,
  Storage,
  Speed,
  TrendingUp,
  Add,
  PlayArrow,
  Stop,
  Settings,
  Visibility,
  Warning,
  CheckCircle,
  Error,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import axiosClient from "../api/axiosClient";

interface DashboardStats {
  activeProjects: number;
  totalInstances: number;
  monthlyExecutions: number;
  subscriptionTier: string;
  maxProjects: number;
  maxInstances: number;
  maxExecutions: number;
}

interface RecentProject {
  id: number;
  name: string;
  description: string;
  status: "active" | "stopped" | "deploying";
  provider: string;
  instanceCount: number;
  lastActivity: string;
  estimatedCost: number;
}

interface ResourceSummary {
  totalInstances: number;
  runningInstances: number;
  stoppedInstances: number;
  providers: { [key: string]: number };
  regions: { [key: string]: number };
}

const Dashboard: React.FC = () => {
  const theme = useTheme();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentProjects, setRecentProjects] = useState<RecentProject[]>([]);
  const [resourceSummary, setResourceSummary] =
    useState<ResourceSummary | null>(null);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    try {
      setLoading(true);

      // Charger les sessions (projets)
      const sessionsResponse = await axiosClient.get("/sessions/list");
      const sessions = sessionsResponse.data;

      // Charger toutes les ressources
      const resourcesResponse = await axiosClient.get(
        "/resources/list_all_resources",
        {
          params: { session_id: sessions[0]?.id || 1 }, // Utiliser la première session pour l'exemple
        },
      );

      const { cloud_resources = [], database_resources = [] } =
        resourcesResponse.data;
      const allResources = [...cloud_resources, ...database_resources];

      // Construire les stats
      // Stats simplifiées sans abonnement
      const dashboardStats: DashboardStats = {
        activeProjects: sessions.length,
        totalInstances: allResources.length,
        monthlyExecutions: 0,
        subscriptionTier: "free",
        maxProjects: Math.max(sessions.length || 1, 3),
        maxInstances: Math.max(allResources.length || 1, 5),
        maxExecutions: 100,
      };

      // Construire les projets récents (mock data pour l'exemple)
      const mockProjects: RecentProject[] = sessions
        .slice(0, 4)
        .map((session: any, index: number) => ({
          id: session.id,
          name: session.description || `Projet ${session.id}`,
          description: session.request_text || "Infrastructure cloud",
          status:
            index === 0 ? "active" : index === 1 ? "deploying" : "stopped",
          provider: session.provider || "aws",
          instanceCount: Math.floor(Math.random() * 5) + 1,
          lastActivity: new Date(
            Date.now() - Math.random() * 86400000 * 7,
          ).toISOString(),
          estimatedCost: Math.floor(Math.random() * 50) + 10,
        }));

      // Construire le résumé des ressources
      const runningCount = allResources.filter(
        (r: any) => r.state === "running",
      ).length;
      const stoppedCount = allResources.length - runningCount;

      const providerCounts = allResources.reduce((acc: any, resource: any) => {
        const provider = resource.provider || "aws";
        acc[provider] = (acc[provider] || 0) + 1;
        return acc;
      }, {});

      const mockResourceSummary: ResourceSummary = {
        totalInstances: allResources.length,
        runningInstances: runningCount,
        stoppedInstances: stoppedCount,
        providers: providerCounts,
        regions: { "eu-west-1": allResources.length },
      };

      setStats(dashboardStats);
      setRecentProjects(mockProjects);
      setResourceSummary(mockResourceSummary);
    } catch (error) {
      console.error("Erreur chargement dashboard:", error);
    } finally {
      setLoading(false);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "active":
        return <CheckCircle color="success" />;
      case "deploying":
        return <Speed color="warning" />;
      case "stopped":
        return <Stop color="disabled" />;
      default:
        return <Error color="error" />;
    }
  };

  const formatRelativeTime = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const hours = Math.floor(diff / (1000 * 60 * 60));
    const days = Math.floor(hours / 24);

    if (days > 0) return `${days}j`;
    if (hours > 0) return `${hours}h`;
    return "maintenant";
  };

  if (loading) {
    return (
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: {
              xs: "1fr",
              sm: "repeat(2, 1fr)",
              md: "repeat(4, 1fr)",
            },
            gap: 3,
          }}
        >
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} variant="rectangular" height={120} />
          ))}
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" gutterBottom fontWeight={700}>
          Dashboard
        </Typography>
        <Typography variant="h6" color="text.secondary">
          Vue d'ensemble de votre infrastructure DevOps
        </Typography>
      </Box>

      {/* Stats Cards */}
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: {
            xs: "1fr",
            sm: "repeat(2, 1fr)",
            md: "repeat(4, 1fr)",
          },
          gap: 3,
          mb: 4,
        }}
      >
        <Card
          sx={{
            background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
            color: "white",
          }}
        >
          <CardContent>
            <Box sx={{ display: "flex", alignItems: "center" }}>
              <Avatar sx={{ bgcolor: alpha("#fff", 0.2), mr: 2 }}>
                <CloudQueue />
              </Avatar>
              <Box sx={{ flex: 1 }}>
                <Typography variant="h4" fontWeight={700}>
                  {stats?.activeProjects ?? 0}
                  {stats?.maxProjects !== -1 && `/${stats?.maxProjects}`}
                </Typography>
                <Typography variant="body2" sx={{ opacity: 0.9 }}>
                  Projets Actifs
                </Typography>
                {stats?.maxProjects !== -1 && (
                  <LinearProgress
                    variant="determinate"
                    value={
                      ((stats?.activeProjects ?? 0) /
                        (stats?.maxProjects ?? 1)) *
                      100
                    }
                    sx={{
                      mt: 1,
                      bgcolor: alpha("#fff", 0.2),
                      "& .MuiLinearProgress-bar": { bgcolor: "#fff" },
                    }}
                  />
                )}
              </Box>
            </Box>
          </CardContent>
        </Card>

        <Card
          sx={{
            background: "linear-gradient(135deg, #f093fb 0%, #f5576c 100%)",
            color: "white",
          }}
        >
          <CardContent>
            <Box sx={{ display: "flex", alignItems: "center" }}>
              <Avatar sx={{ bgcolor: alpha("#fff", 0.2), mr: 2 }}>
                <Storage />
              </Avatar>
              <Box sx={{ flex: 1 }}>
                <Typography variant="h4" fontWeight={700}>
                  {stats?.totalInstances ?? 0}
                  {stats?.maxInstances !== -1 && `/${stats?.maxInstances}`}
                </Typography>
                <Typography variant="body2" sx={{ opacity: 0.9 }}>
                  Instances
                </Typography>
                {stats?.maxInstances !== -1 &&
                  (stats?.totalInstances ?? 0) > (stats?.maxInstances ?? 0) && (
                    <Box sx={{ display: "flex", alignItems: "center", mt: 1 }}>
                      <Warning sx={{ fontSize: 16, mr: 0.5 }} />
                      <Typography variant="caption">Limite dépassée</Typography>
                    </Box>
                  )}
              </Box>
            </Box>
          </CardContent>
        </Card>

        <Card
          sx={{
            background: "linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)",
            color: "white",
          }}
        >
          <CardContent>
            <Box sx={{ display: "flex", alignItems: "center" }}>
              <Avatar sx={{ bgcolor: alpha("#fff", 0.2), mr: 2 }}>
                <Speed />
              </Avatar>
              <Box sx={{ flex: 1 }}>
                <Typography variant="h4" fontWeight={700}>
                  {stats?.monthlyExecutions ?? 0}/{stats?.maxExecutions ?? 0}
                </Typography>
                <Typography variant="body2" sx={{ opacity: 0.9 }}>
                  Exécutions ce mois
                </Typography>
                <LinearProgress
                  variant="determinate"
                  value={
                    ((stats?.monthlyExecutions ?? 0) /
                      (stats?.maxExecutions ?? 1)) *
                    100
                  }
                  sx={{
                    mt: 1,
                    bgcolor: alpha("#fff", 0.2),
                    "& .MuiLinearProgress-bar": { bgcolor: "#fff" },
                  }}
                />
              </Box>
            </Box>
          </CardContent>
        </Card>
      </Box>

      {/* Content Grid */}
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: {
            xs: "1fr",
            lg: "2fr 1fr",
          },
          gap: 3,
        }}
      >
        {/* Sessions recentes */}
        <Card>
          <CardContent>
            <Box
              sx={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                mb: 3,
              }}
            >
              <Typography variant="h6" fontWeight={600}>
                Sessions DAC récentes
              </Typography>
              <Button
                startIcon={<Add />}
                variant="contained"
                onClick={() => navigate("/chat")}
              >
                Nouveau Chat
              </Button>
            </Box>

            <Stack spacing={2}>
              {recentProjects.map((project) => (
                <Card
                  key={project.id}
                  variant="outlined"
                  sx={{
                    cursor: "pointer",
                    "&:hover": {
                      boxShadow: theme.shadows[4],
                      transform: "translateY(-1px)",
                    },
                    transition: "all 0.2s ease",
                  }}
                  onClick={() => navigate("/chat")}
                >
                  <CardContent sx={{ py: 2 }}>
                    <Box
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                      }}
                    >
                      <Box
                        sx={{ display: "flex", alignItems: "center", flex: 1 }}
                      >
                        {getStatusIcon(project.status)}
                        <Box sx={{ ml: 2, flex: 1 }}>
                          <Typography variant="subtitle1" fontWeight={600}>
                            {project.name}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            {project.description}
                          </Typography>
                        </Box>
                      </Box>

                      <Box
                        sx={{ display: "flex", alignItems: "center", gap: 2 }}
                      >
                        <Chip
                          label={project.provider.toUpperCase()}
                          size="small"
                          color="primary"
                          variant="outlined"
                        />
                        <Typography variant="body2" color="text.secondary">
                          {project.instanceCount} instances
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          {formatRelativeTime(project.lastActivity)}
                        </Typography>
                        <Typography variant="body2" fontWeight={600}>
                          ~{project.estimatedCost}€/mois
                        </Typography>

                        <Box sx={{ display: "flex", gap: 1 }}>
                          <IconButton
                            size="small"
                            onClick={(e) => {
                              e.stopPropagation();
                              navigate("/chat");
                            }}
                          >
                            <Visibility />
                          </IconButton>
                          <IconButton
                            size="small"
                            color={
                              project.status === "active" ? "error" : "success"
                            }
                            onClick={(e) => {
                              e.stopPropagation();
                              // Toggle project status
                            }}
                          >
                            {project.status === "active" ? (
                              <Stop />
                            ) : (
                              <PlayArrow />
                            )}
                          </IconButton>
                        </Box>
                      </Box>
                    </Box>
                  </CardContent>
                </Card>
              ))}

              {recentProjects.length === 0 && (
                <Box sx={{ textAlign: "center", py: 4 }}>
                  <Typography variant="h6" color="text.secondary" gutterBottom>
                    Aucune session trouvée
                  </Typography>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{ mb: 2 }}
                  >
                    Lancez le chat DAC pour créer votre première infrastructure
                  </Typography>
                  <Button
                    variant="contained"
                    startIcon={<Add />}
                    onClick={() => navigate("/chat")}
                  >
                    Ouvrir le Chat
                  </Button>
                </Box>
              )}
            </Stack>
          </CardContent>
        </Card>

        {/* Resource Summary */}
        <Stack spacing={3}>
          {/* Actions Rapides */}
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={600} gutterBottom>
                Actions Rapides
              </Typography>
              <Stack spacing={2}>
                <Button
                  fullWidth
                  variant="outlined"
                  startIcon={<Add />}
                  onClick={() => navigate("/chat")}
                >
                  Nouveau Chat
                </Button>
                <Button
                  fullWidth
                  variant="outlined"
                  startIcon={<CloudQueue />}
                  onClick={() => navigate("/resources")}
                >
                  Voir Ressources
                </Button>
                <Button
                  fullWidth
                  variant="outlined"
                  startIcon={<Storage />}
                  onClick={() => navigate("/resources")}
                >
                  Voir Ressources
                </Button>
                <Button
                  fullWidth
                  variant="outlined"
                  startIcon={<Settings />}
                  onClick={() => navigate("/settings")}
                >
                  Paramètres
                </Button>
              </Stack>
            </CardContent>
          </Card>

          {/* Resources Summary */}
          {resourceSummary && (
            <Card>
              <CardContent>
                <Typography variant="h6" fontWeight={600} gutterBottom>
                  Résumé des Ressources
                </Typography>

                <Box sx={{ mb: 3 }}>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    gutterBottom
                  >
                    Status des Instances
                  </Typography>
                  <Box
                    sx={{
                      display: "flex",
                      justifyContent: "space-between",
                      mb: 1,
                    }}
                  >
                    <Typography variant="body2">
                      En marche: {resourceSummary.runningInstances}
                    </Typography>
                    <Typography variant="body2">
                      Arrêtées: {resourceSummary.stoppedInstances}
                    </Typography>
                  </Box>
                  <LinearProgress
                    variant="determinate"
                    value={
                      resourceSummary.totalInstances
                        ? (resourceSummary.runningInstances /
                            resourceSummary.totalInstances) *
                          100
                        : 0
                    }
                    sx={{ height: 8, borderRadius: 1 }}
                  />
                </Box>

                <Box sx={{ mb: 2 }}>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    gutterBottom
                  >
                    Providers
                  </Typography>
                  {Object.entries(resourceSummary.providers).map(
                    ([provider, count]) => (
                      <Box
                        key={provider}
                        sx={{
                          display: "flex",
                          justifyContent: "space-between",
                        }}
                      >
                        <Typography variant="body2">
                          {provider.toUpperCase()}
                        </Typography>
                        <Typography variant="body2">{count}</Typography>
                      </Box>
                    ),
                  )}
                </Box>
              </CardContent>
            </Card>
          )}
        </Stack>
      </Box>
    </Container>
  );
};

export default Dashboard;
