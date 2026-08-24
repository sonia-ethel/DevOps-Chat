import { 
  Box, 
  Typography, 
  Button, 
  Paper, 
  alpha, 
  Avatar,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
} from '@mui/material';
import { 
  Warning,
  Security,
  CloudQueue,
  Chat,
  ArrowForward,
} from '@mui/icons-material';
import { useOnboarding } from '../contexts/OnboardingContext';

export default function OnboardingRequired() {
  const { startOnboarding, onboardingStatus } = useOnboarding();

  const handleStartOnboarding = () => {
    console.log(' Starting onboarding from OnboardingRequired page');
    startOnboarding();
  };

  // Si l'onboarding est en cours, ne pas afficher cette page
  if (onboardingStatus === 'in_progress') {
    return null;
  }

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        bgcolor: 'background.default',
        backgroundImage: 'linear-gradient(180deg, #0f172a 0%, #1e293b 100%)',
        p: 2,
      }}
    >
      <Paper
        elevation={0}
        sx={{
          maxWidth: 600,
          width: '100%',
          p: 4,
          bgcolor: alpha('#1e293b', 0.8),
          backdropFilter: 'blur(20px)',
          border: '1px solid',
          borderColor: alpha('#475569', 0.3),
          borderRadius: 3,
          textAlign: 'center',
        }}
      >
        {/* Warning Icon */}
        <Avatar
          sx={{
            width: 80,
            height: 80,
            mx: 'auto',
            mb: 3,
            bgcolor: alpha('#f59e0b', 0.2),
            border: '2px solid',
            borderColor: alpha('#f59e0b', 0.3),
            '& svg': { fontSize: '2.5rem', color: '#f59e0b' },
          }}
        >
          <Warning />
        </Avatar>

        {/* Header */}
        <Typography variant="h4" fontWeight={700} color="text.primary" gutterBottom>
          Configuration AWS requise
        </Typography>
        
        <Typography variant="h6" color="text.secondary" sx={{ mb: 4, lineHeight: 1.6 }}>
          Pour accéder au chat et utiliser les fonctionnalités DevOps, vous devez d'abord 
          configurer vos credentials AWS.
        </Typography>

        {/* Features List */}
        <Paper
          elevation={0}
          sx={{
            p: 3,
            mb: 4,
            bgcolor: alpha('#334155', 0.3),
            border: '1px solid',
            borderColor: alpha('#475569', 0.2),
            borderRadius: 2,
            textAlign: 'left',
          }}
        >
          <Typography variant="h6" fontWeight={600} color="text.primary" sx={{ mb: 2 }}>
            Ce qui vous attend après la configuration :
          </Typography>
          
          <List sx={{ p: 0 }}>
            <ListItem sx={{ px: 0, py: 0.5 }}>
              <ListItemIcon sx={{ minWidth: 36 }}>
                <Chat sx={{ color: 'primary.main', fontSize: 20 }} />
              </ListItemIcon>
              <ListItemText
                primary="Assistant DevOps intelligent"
                secondary="Conversations naturelles pour gérer votre infrastructure"
                primaryTypographyProps={{ variant: 'body1', fontWeight: 500 }}
                secondaryTypographyProps={{ variant: 'body2', fontSize: '0.875rem' }}
              />
            </ListItem>
            
            <ListItem sx={{ px: 0, py: 0.5 }}>
              <ListItemIcon sx={{ minWidth: 36 }}>
                <CloudQueue sx={{ color: 'secondary.main', fontSize: 20 }} />
              </ListItemIcon>
              <ListItemText
                primary="Déploiement automatisé"
                secondary="Créez et gérez vos ressources AWS facilement"
                primaryTypographyProps={{ variant: 'body1', fontWeight: 500 }}
                secondaryTypographyProps={{ variant: 'body2', fontSize: '0.875rem' }}
              />
            </ListItem>
            
            <ListItem sx={{ px: 0, py: 0.5 }}>
              <ListItemIcon sx={{ minWidth: 36 }}>
                <Security sx={{ color: 'success.main', fontSize: 20 }} />
              </ListItemIcon>
              <ListItemText
                primary="Sécurité garantie"
                secondary="Vos credentials sont chiffrés et sécurisés"
                primaryTypographyProps={{ variant: 'body1', fontWeight: 500 }}
                secondaryTypographyProps={{ variant: 'body2', fontSize: '0.875rem' }}
              />
            </ListItem>
          </List>
        </Paper>

        {/* Call to Action */}
        <Button
          variant="contained"
          size="large"
          endIcon={<ArrowForward />}
          onClick={handleStartOnboarding}
          sx={{
            py: 1.5,
            px: 4,
            fontSize: '1.1rem',
            fontWeight: 600,
            borderRadius: 3,
            background: 'linear-gradient(135deg, #f59e0b 0%, #f97316 100%)',
            '&:hover': {
              background: 'linear-gradient(135deg, #d97706 0%, #ea580c 100%)',
              transform: 'translateY(-2px)',
              boxShadow: '0 12px 40px rgba(245, 158, 11, 0.4)',
            },
            transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          }}
        >
          Configurer AWS maintenant
        </Button>

        <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
          La configuration ne prend que quelques minutes
        </Typography>
      </Paper>
    </Box>
  );
}