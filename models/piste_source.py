# -*- coding: utf-8 -*-
from odoo import models, fields, api  # type: ignore
from odoo.exceptions import ValidationError  # type: ignore
import requests
import json
import logging
from datetime import datetime, timedelta
import random

_logger = logging.getLogger(__name__)


# ================================
# Modèle pour les mots-clés
# ================================
class PisteKeyword(models.Model):
    _name = 'piste.keyword'
    _description = 'Mot-clé'

    name = fields.Char(string="Mot-clé", required=True)


# ================================
# Modèle Veille commerciale
# ================================
class PisteSource(models.Model):
    _name = 'piste.source'
    _description = 'Veille commerciale'
    _rec_name = 'name'
    _order = 'name'

    # ===== IDENTIFICATION =====
    name = fields.Char(string="Nom de la veille", required=True)
    description = fields.Text(string="Description / Notes")
    active = fields.Boolean(string="Actif", default=True)

    # ===== MOTS-CLÉS =====
    keywords_required_ids = fields.Many2many(
        'piste.keyword',
        string="Mots-clés obligatoires",
        required=True
    )

    # ===== PLATEFORMES =====
    platform_marches_publics = fields.Boolean(string="Marchés Publics Gouv (Officiel)")
    platform_emarches = fields.Boolean(string="e-marchespublics.com")
    platform_francetenders = fields.Boolean(string="France Tenders")
    platform_appelaprojets = fields.Boolean(string="Appel à Projets")
    platform_marchesonline = fields.Boolean(string="Marchés Online (Payant)")
    platform_tenderimpulse = fields.Boolean(string="Tender Impulse (Payant)")
    platform_globaltenders = fields.Boolean(string="Global Tenders (Payant)")
    platform_deepbloo = fields.Boolean(string="DeepBloo (Payant)")
    platform_batieu = fields.Boolean(string="Bati EU (Payant)")
    platform_boamp = fields.Boolean(string="BOAMP (Bulletin Officiel)")
    platform_ted = fields.Boolean(string="TED - Tenders Electronic Daily (EU)")

    # ===== CRITÈRES COMMERCIAUX =====
    budget_min = fields.Integer(string="Budget minimum (€)")
    budget_max = fields.Integer(string="Budget maximum (€)")

    duration_short = fields.Boolean(string="Court terme (< 3 mois)")
    duration_medium = fields.Boolean(string="Moyen terme (3-6 mois)")
    duration_long = fields.Boolean(string="Long terme (6+ mois)")

    client_pme = fields.Boolean(string="PME / Startups")
    client_large = fields.Boolean(string="Grande entreprise")

    # ===== LOCALISATION =====
    geo_zones = fields.Many2many('res.country', string="Zones géographiques", required=True)

    # ===== UTILISATEUR QUI CRÉE =====
    creator_id = fields.Many2one(
        'res.users',
        string="Créé par",
        default=lambda self: self.env.user,
        required=True
    )

    # ===== AUTOMATISATION =====
    automation_type = fields.Selection(
        [('manual', 'Manuel'), ('auto', 'Automatique')],
        string="Type de veille",
        required=True,
        default='manual'
    )

    auto_frequency = fields.Selection([
        ('1h', 'Toutes les heures'),
        ('6h', 'Toutes les 6 heures'),
        ('12h', 'Toutes les 12 heures'),
        ('24h', 'Une fois par jour'),
        ('custom', 'Personnalisée'),
    ], string="Fréquence automatique")

    auto_date = fields.Date(string="Date de début")
    auto_time = fields.Float(string="Heure (ex: 14.30)")
    auto_repeat = fields.Selection([
        ('daily', 'Chaque jour'),
        ('2days', 'Chaque 2 jours'),
        ('weekly', 'Chaque semaine'),
        ('monthly', 'Chaque mois'),
    ], string="Répétition")

    # ===== NOTIFICATIONS =====
    notify_email = fields.Boolean(string="Notification par email", default=False)
    notify_odoo = fields.Boolean(string="Notification Odoo", default=True)
    notify_emails = fields.Text(string="Emails des destinataires")

    # ===== RELATION AVEC LES OFFRES =====
    offer_ids = fields.One2many('piste.offer', 'source_id', string='Offres trouvées')
    offer_count = fields.Integer(string="Nombre d'offres", compute='_compute_offer_count', store=True)
    last_search_date = fields.Datetime(string="Dernière recherche")

    # ===== MÉTHODES =====
    @api.depends('offer_ids')
    def _compute_offer_count(self):
        for source in self:
            source.offer_count = len(source.offer_ids)

    def action_view_offers(self):
        return {
            'type': 'ir.actions.act_window',
            'name': f'Offres - {self.name}',
            'res_model': 'piste.offer',
            'view_mode': 'tree,form',
            'domain': [('source_id', '=', self.id)],
            'context': {'default_source_id': self.id}
        }

    # ===== VALIDATION =====
    @api.constrains(
        'keywords_required_ids',
        'platform_marches_publics', 'platform_emarches', 'platform_francetenders',
        'platform_appelaprojets', 'platform_marchesonline', 'platform_tenderimpulse',
        'platform_globaltenders', 'platform_deepbloo', 'platform_batieu',
        'platform_boamp', 'platform_ted',
        'automation_type', 'auto_frequency', 'auto_date', 'auto_time', 'auto_repeat'
    )
    def _check_required_fields(self):
        for record in self:
            # 1️⃣ Au moins un mot-clé obligatoire
            if not record.keywords_required_ids:
                raise ValidationError("Vous devez sélectionner au moins un mot-clé obligatoire.")

            # 2️⃣ Au moins une plateforme
            platforms = [
                record.platform_marches_publics,
                record.platform_emarches,
                record.platform_francetenders,
                record.platform_appelaprojets,
                record.platform_marchesonline,
                record.platform_tenderimpulse,
                record.platform_globaltenders,
                record.platform_deepbloo,
                record.platform_batieu,
                record.platform_boamp,
                record.platform_ted
            ]
            if not any(platforms):
                raise ValidationError("Vous devez sélectionner au moins une plateforme.")

            # 3️⃣ Validation automatisation si type = auto
            if record.automation_type == 'auto':
                if not record.auto_frequency:
                    raise ValidationError("Vous devez choisir une fréquence pour l'automatisation.")

                # Si fréquence personnalisée, tous les autres champs deviennent obligatoires
                if record.auto_frequency == 'custom':
                    if not record.auto_date:
                        raise ValidationError("Vous devez choisir une date de début pour l'automatisation personnalisée.")
                    if record.auto_time in (None, ''):
                        raise ValidationError("Vous devez choisir une heure pour l'automatisation personnalisée.")
                    if not record.auto_repeat:
                        raise ValidationError("Vous devez choisir la répétition pour l'automatisation personnalisée.")



    # ===== BOUTON POUR ENVOYER LA VEILLE À N8N =====
    def action_run_scrape(self):
        """
        Bouton Odoo : envoie les données de la veille au webhook n8n
        """
        # 🎯 ÉTAPE 1 : URL du webhook N8N
        n8n_webhook_url = "http://localhost:5678/webhook-test/piste-run"
        
        for source in self:
            # 🎯 ÉTAPE 2 : Préparation du JSON à envoyer
            payload = {
                'id': source.id,                    # ID de la veille
                'name': source.name,                # Ex: "Projets Odoo France"
                'keywords_required': [              # Mots-clés sélectionnés
                    kw.name for kw in source.keywords_required_ids
                ],
                'platforms': {                      # Plateformes cochées
                    'marches_publics': source.platform_marches_publics,
                    'emarches': source.platform_emarches,
                    'boamp': source.platform_boamp,
                    # ... toutes les plateformes
                },
                'budget_min': source.budget_min,    # Filtre budget
                'budget_max': source.budget_max,
                'geo_zones': [                      # Pays sélectionnés
                    c.code for c in source.geo_zones
                ],
                'frequency': source.auto_frequency, # Fréquence (6h, 12h...)
            }
            
            # 🎯 ÉTAPE 3 : Envoi HTTP POST vers N8N
            try:
                response = requests.post(
                    n8n_webhook_url,                    # URL du webhook
                    headers={'Content-Type': 'application/json'},
                    data=json.dumps(payload),           # Données en JSON
                    timeout=10                          # Max 10 secondes
                )
                # 🎯 ÉTAPE 4 : Log du succès
                _logger.info("Scrape envoyé à n8n : %s -> Status %s", 
                            source.name, response.status_code)
            except Exception as e:
                # 🎯 ÉTAPE 5 : Log de l'erreur
                _logger.error("Erreur lors de l'envoi à n8n : %s", str(e))