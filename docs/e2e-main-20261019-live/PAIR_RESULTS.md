# Formal Job Pair Results

这些是原正式 Job 的真实结果。C8 的错误判定保留；修复后独立真实重放见 targeted-c8-live-result.json，不替换本表。完整 Agent JSON 见 pair-audit.json。

## C1 × Reference 1

Claim ID: `claim:79adf1fa6aad6a5f87f54e8bfd407b2a7e1a64cc1d46bff70f2686e53156cffe`

Reference ID: `reference:manuscript:420a8ea6573ba22c5f4852e0ee08722b09ebcc351081def1ee53665770cd3d1f:grobid-0.9.1-body-prose-v1:0`

Examples of key secondary endpoints include the durations of supplemental oxygen usage, invasive mechanical ventilation, hospitalization, and ICU stay.

Status: completed / VERIFIED

Original adjudicator: OVERSTATED / 0.84; domain validated: OVERSTATED / 0.7392

The supplied Remdesivir Outcomes section states, "The key secondary outcome was clinical status at day 15, as assessed on the ordinal scale," and then lists "number of days with supplemental oxygen," "number of days with invasive ventilation or ECMO," and "number of days of hospitalization" among "Other secondary outcomes." Thus the duration measures are supported as secondary outcomes, not as key secondary endpoints. Results chunks likewise report duration findings for oxygen use, invasive ventilation/ECMO, and hospital stay. However, no supplied chunk mentions ICU stay, so that specific example is unsupported by the provided evidence. The appropriate correction is to call these secondary endpoints rather than key secondary endpoints, and to remove or qualify ICU stay unless another source supports it.

Warnings: ["ORIGINAL_CITATION_VERSION_UNCONFIRMED"]

### evidence:672bf77e7f5babcde76ed435ae3b3686dce0c4e8398f311336c6edd8a9609c0d

Section: Outcomes; PaperQA score: 8; Source: source:126a2d33afafb4cc04617e9aa26a2d0d1781478eaf5ba58c012d45fa615a08ee

The key secondary outcome was clinical status at day 15, as assessed on the ordinal scale. Other secondary outcomes included the time to improvement of one category and of two categories from the baseline ordinal score; clinical status as assessed on the ordinal scale at days 3, 5, 8, 11, 15, 22, and 29; mean change in status on the ordinal scale from day 1 to days 3, 5, 8, 11, 15, 22, and 29; time to discharge or National Early Warning Score of 2 or less (maintained for 24 hours), whichever occurred first; change in the National Early Warning Score from day 1 to days 3, 5, 8, 11, 15, 22, and 29; number of days with supplemental oxygen, with noninvasive ventilation or high-flow oxygen, and with invasive ventilation or ECMO up to day 29 (if these were being used at baseline); the incidence and duration of new oxygen use, of noninvasive ventilation or high-flow oxygen, and of invasive ventilation or ECMO; number of days of hospitalization up to day 29; and mortality at 14 and 28 days aft

### evidence:c2afe729a4462df1f0c17da08429db55c7f925c5bbe389bfacfe12894fe6838c

Section: Outcomes; PaperQA score: 8; Source: source:126a2d33afafb4cc04617e9aa26a2d0d1781478eaf5ba58c012d45fa615a08ee

and duration of new oxygen use, of noninvasive ventilation or high-flow oxygen, and of invasive ventilation or ECMO; number of days of hospitalization up to day 29; and mortality at 14 and 28 days after enrollment. Secondary safety outcome measures included grade 3 and 4 adverse events and serious adverse events that occurred during the trial, discontinuation or temporary suspension of infusions, and changes in assessed laboratory values over time.

### evidence:e056dd6d89f8ce20f1b9b4d06294ecdf57782ce9e823800c362d8926448908a4

Section: Table 3. Additional Secondary Outcomes.; PaperQA score: 6; Source: source:126a2d33afafb4cc04617e9aa26a2d0d1781478eaf5ba58c012d45fa615a08ee

Among the 913 patients receiving oxygen at enrollment, those in the remdesivir group continued to receive oxygen for fewer days than patients in the placebo group (median, 13 days vs. 21 days), and the incidence of new oxygen use among patients who were not receiving oxygen at enrollment was lower in the remdesivir group than in the placebo group (incidence, 36% [95% CI, 26 to 47] vs. 44% [95% CI, 33 to 57]). For the 193 patients receiving noninvasive ventilation or high-flow oxygen at enrollment, the median duration of use of these interventions was 6 days in both the remdesivir and placebo groups. Among the 573 patients who were not receiving noninvasive ventilation, high-flow oxygen, invasive ventilation, or ECMO at baseline, the incidence of new noninvasive ventilation or high-flow oxygen use was lower in the remdesivir group than in the placebo group (17% [95% CI, 13 to 22] vs. 24% [95% CI, 19 to 30]). Among the 285 patients who were receiving mechanical ventilation or ECMO at enr

### evidence:42fc8609c343f052ace728a7e80c251b897b2cb6591728d739a9ca8fcc123700

Section: Discussion; PaperQA score: 5; Source: source:126a2d33afafb4cc04617e9aa26a2d0d1781478eaf5ba58c012d45fa615a08ee

of one and of two ordinal scale categories, a shorter time to discharge or to a sustained National Early Warning Score of 2 or lower, and a shorter length of initial hospital stay (median, 12 days vs. 17 days). All-cause mortality was 11.4% with remdesivir and 15.2% with placebo (hazard ratio, 0.73; 95% CI, 0.52 to 1.03).

### evidence:b9368dc7bd0c60b562966a4e7c38580ba1e27f0e1b37759e46515102c0f86e12

Section: Table 3. Additional Secondary Outcomes.; PaperQA score: 5; Source: source:126a2d33afafb4cc04617e9aa26a2d0d1781478eaf5ba58c012d45fa615a08ee

gen use was lower in the remdesivir group than in the placebo group (17% [95% CI, 13 to 22] vs. 24% [95% CI, 19 to 30]). Among the 285 patients who were receiving mechanical ventilation or ECMO at enrollment, patients in the remdesivir group received these interventions for fewer subsequent days than those in the placebo group (median, 17 days vs. 20 days), and the incidence of new mechanical ventilation or ECMO use among the 766 patients who were not receiving these interventions at enrollment was lower in the remdesivir group than in the placebo group (13% [95% CI, 10 to 17] vs. 23% [95% CI, 19 to 27]) (
Table 3
).

## C1 × Reference 2

Claim ID: `claim:79adf1fa6aad6a5f87f54e8bfd407b2a7e1a64cc1d46bff70f2686e53156cffe`

Reference ID: `reference:manuscript:420a8ea6573ba22c5f4852e0ee08722b09ebcc351081def1ee53665770cd3d1f:grobid-0.9.1-body-prose-v1:1`

Examples of key secondary endpoints include the durations of supplemental oxygen usage, invasive mechanical ventilation, hospitalization, and ICU stay.

Status: completed / VERIFIED

Original adjudicator: INSUFFICIENT / 0.64; domain validated: INSUFFICIENT / 0

The available chunk from the cited remdesivir trial states that the secondary endpoint was the proportion of patients with adverse events and that time to clinical improvement, time to recovery, and time to modified recovery were prespecified exploratory endpoints (chunk evidence:299dc5d0a50d82608b4bfd517b3b2d25f0af814e9d933a4c612b99644aea7380). That does not match the claim's examples for this specific trial, but the claim is a generic multi-reference illustration and only one cited source is supplied. No chunk explicitly addresses duration of ICU stay or hospitalization as key secondary endpoints, and no chunk rules out that the other cited trials list such endpoints. Thus the evidence cannot settle the core claim, and the mismatch is not enough for CONTRADICTS.

Warnings: ["Suggested correction removed because verdict is INSUFFICIENT.","ORIGINAL_CITATION_VERSION_UNCONFIRMED"]

### evidence:299dc5d0a50d82608b4bfd517b3b2d25f0af814e9d933a4c612b99644aea7380

Section: End Points; PaperQA score: 7; Source: source:83282512bdeb9bc5f4b722420570deeb80d9e2d07f873f45950e2bbc85f8a131

oxygen nor ongoing medical care (other than that specified in the protocol for remdesivir administration); and 7, not hospitalized (see Table S1 in the
Supplementary Appendix
, available at NEJM.org).

The secondary end point of the trial was the proportion of patients with adverse events that occurred on or after the first dose of remdesivir for up to 30 days after the last dose. Prespecified exploratory end points included the time to clinical improvement (defined as an improvement of at least 2 points from baseline on the 7-point ordinal scale), the time to recovery (defined by the National Institute of Allergy and Infectious Diseases [NIAID] as an improvement from a baseline score of 2 to 5 to a score of 6 or 7), the time to modified recovery (defined as an improvement from a baseline score of 2 to 4 to a score of 5 to 7 or from a score of 5 to a score of 6 or 7), and death from any cause.

### evidence:f655834dce6916119aac724773fb5551af0d814c725138b19dd3a8639d8ea14e

Section: Efficacy; PaperQA score: 3; Source: source:83282512bdeb9bc5f4b722420570deeb80d9e2d07f873f45950e2bbc85f8a131

We conducted a post hoc analysis to determine whether any subpopulation might have benefitted from receiving more than 5 days of therapy with remdesivir (
Figure 2
). The oxygen-support status among all patients still hospitalized on day 5 was noted. Patients were then evaluated according to original treatment assignment for day 14 outcomes, to determine the effect of an additional 5 days of treatment with remdesivir. Among patients receiving mechanical ventilation or ECMO at day 5, 40% (10 of 25) in the 5-day group had died by day 14, as compared with 17% (7 of 41) in the 10-day group (
Figure 2
). Treatment with remdesivir beyond 5 days among patients who were receiving noninvasive positive-pressure ventilation or high-flow oxygen, receiving low-flow oxygen, or breathing ambient air did not appear to improve outcomes. In multivariate analysis, characteristics associated with shorter time to clinical improvement were an age of less than 65 years, black and white race, a baseline oxyge

### evidence:02a0a9726b730f5f6e2da75239855203b0a51a1aba5f6cc4dbb18d4c66d2dd9e

Section: Trial Design and Oversight; PaperQA score: 2; Source: source:83282512bdeb9bc5f4b722420570deeb80d9e2d07f873f45950e2bbc85f8a131

patients, including a cohort of patients receiving mechanical ventilation (results of the extension phase are not reported here). All versions of the
protocol
and summaries of the amendments are available at NEJM.org.

### evidence:1be94dcb779594533aaf20ccd2d7f3b03a7fcb59835d149df3cf52d962952e8d

Section: Efficacy; PaperQA score: 2; Source: source:83282512bdeb9bc5f4b722420570deeb80d9e2d07f873f45950e2bbc85f8a131

not appear to improve outcomes. In multivariate analysis, characteristics associated with shorter time to clinical improvement were an age of less than 65 years, black and white race, a baseline oxygen requirement of low-flow oxygen or ambient air, no use of a biologic medication, and enrollment outside Italy (Tables S3 and S4).

## C1 × Reference 3

Claim ID: `claim:79adf1fa6aad6a5f87f54e8bfd407b2a7e1a64cc1d46bff70f2686e53156cffe`

Reference ID: `reference:manuscript:420a8ea6573ba22c5f4852e0ee08722b09ebcc351081def1ee53665770cd3d1f:grobid-0.9.1-body-prose-v1:2`

Examples of key secondary endpoints include the durations of supplemental oxygen usage, invasive mechanical ventilation, hospitalization, and ICU stay.

Status: completed / VERIFIED

Original adjudicator: SUPPORTS / 0.9; domain validated: SUPPORTED / 0.9

Both evidence chunks show that the cited trial measured and reported durations of oxygen therapy, mechanical ventilation, hospitalization, and ICU stay as non-primary clinical outcomes. The claim's examples are therefore faithful to the source's endpoint domains. The omission of 'in survivors' and the added 'invasive' qualifier are ordinary summarization details rather than material scope changes.

Warnings: ["ORIGINAL_CITATION_VERSION_UNCONFIRMED"]

### evidence:ee82346f1003b1b0dba7978e7236872114fa1cb0604f3ef6c26325c9c4b1f56e

Section: Table 3. Outcomes in the Intention-to-Treat Population. * .; PaperQA score: 9; Source: source:13a7183272ddf96daa7bc2e2ea9e956b3cb7f2fcaae81ffa7d412154cbdc5c6f

azard ratio for clinical improvement was estimated by Cox proportional-risk model.

This total includes 3 patients who died within 24 hours after randomization and did not receive lopinavir–ritonavir.

Patients in the lopinavir–ritonavir group had a shorter stay in the intensive care unit (ICU) than those in the standard-care group (median, 6 days vs. 11 days; difference, −5 days; 95% CI, −9 to 0), and the duration from randomization to hospital discharge was numerically shorter (median, 12 days vs. 14 days; difference, 1 day; 95% CI, 0 to 3). In addition, the percentage of patients with clinical improvement at day 14 was higher in the lopinavir–ritonavir group than in the standard-care group (45.5% vs. 30.0%; difference, 15.5 percentage points; 95% CI, 2.2 to 28.8) (Fig. S5). There were no significant differences for other outcomes such as duration of oxygen therapy, duration of hospitalization, and time from randomization to death.

### evidence:60258fa99aded6de7eb6f6dae53ea0511919dca45c8bac9b45c48e524103a598

Section: Outcome Measures; PaperQA score: 7; Source: source:13a7183272ddf96daa7bc2e2ea9e956b3cb7f2fcaae81ffa7d412154cbdc5c6f

Other clinical outcomes included clinical status as assessed with the seven-category ordinal scale on days 7 and 14, mortality at day 28, the duration of mechanical ventilation, the duration of hospitalization in survivors, and the time (in days) from treatment initiation to death. Virologic measures included the proportions with viral RNA detection over time and viral RNA titer area-under-the-curve (AUC) measurements.

Safety outcomes included adverse events that occurred during treatment, serious adverse events, and premature discontinuation of treatment. Adverse events were classified according to the National Cancer Institute Common Terminology Criteria for Adverse Events, version 4.0.

## C1 × Reference 4

Claim ID: `claim:79adf1fa6aad6a5f87f54e8bfd407b2a7e1a64cc1d46bff70f2686e53156cffe`

Reference ID: `reference:manuscript:420a8ea6573ba22c5f4852e0ee08722b09ebcc351081def1ee53665770cd3d1f:grobid-0.9.1-body-prose-v1:3`

Examples of key secondary endpoints include the durations of supplemental oxygen usage, invasive mechanical ventilation, hospitalization, and ICU stay.

Status: completed / VERIFIED

Original adjudicator: SUPPORTS / 0.72; domain validated: SUPPORTED / 0.72

The claim's core point—that duration endpoints such as oxygen use and hospitalization are key secondary endpoints in this trial context—is directly supported by evidence:a4e072e57dceb48fc58ff35653efe52b2af743158a5cad7a7133cc8a3211462a, which lists 'duration of oxygen therapy' and 'duration of hospital admission' among secondary outcomes, and by evidence:a0e7ace42bb7ad00792e0b3eb3dbed3acf2cc4eb2a6939edf7fe9d3ef8a6c934, which reports length of oxygen support and hospital length of stay. The ventilation-duration element is supported only indirectly because the excerpt is truncated, and ICU-stay duration is not confirmed in the supplied chunks. However, this is an illustrative, multi-citation list rather than a claim that this single source contains all four items, and there is no positive evidence of contradiction, fabrication, or material scope expansion.

Warnings: ["ORIGINAL_CITATION_VERSION_UNCONFIRMED"]

### evidence:a0e7ace42bb7ad00792e0b3eb3dbed3acf2cc4eb2a6939edf7fe9d3ef8a6c934

Section: Figure 2.; PaperQA score: 8; Source: source:f53647d6ec684100e29ff43fc663e167b93ed24f7a69e107ad870468578f5d3c

antly different, but numerically shorter than in those assigned to the control group; however, the number of patients with invasive mechanical ventilation was small. No significant differences were observed between the two groups in length of oxygen support, hospital length of stay, days from randomisation to discharge, days from randomisation to death and distribution of six-category scale at day 7, day 14, and day 28 (
table 3
;
appendix p 9
).

### evidence:a4e072e57dceb48fc58ff35653efe52b2af743158a5cad7a7133cc8a3211462a

Section: Outcomes; PaperQA score: 8; Source: source:f53647d6ec684100e29ff43fc663e167b93ed24f7a69e107ad870468578f5d3c

Secondary outcomes were the proportions of patients in each category of the six-point scale at day 7, 14, and 28 after randomisation; all-cause mortality at day 28; frequency of invasive mechanical ventilation; duration of oxygen therapy; duration of hospital admission; and proportion of patients with nosocomial infection. Virological measures included the proportions of patients with viral RNA detected and viral RNA load (measured by quantitative RT-PCR). Safety outcomes included treatment-emergent adverse events, serious adverse events, and premature discontinuations of study drug.

### evidence:f8c92c0b3def0f960bc7cc8c35a3efa321d92a98ca842f3b30fcbf84b2956de0

Section: Methods; PaperQA score: 2; Source: source:f53647d6ec684100e29ff43fc663e167b93ed24f7a69e107ad870468578f5d3c

We did a randomised, double-blind, placebo-controlled, multicentre trial at ten hospitals in Hubei, China. Eligible patients were adults (aged ≥18 years) admitted to hospital with laboratory-confirmed SARS-CoV-2 infection, with an interval from symptom onset to enrolment of 12 days or less, oxygen saturation of 94% or less on room air or a ratio of arterial oxygen partial pressure to fractional inspired oxygen of 300 mm Hg or less, and radiologically confirmed pneumonia. Patients were randomly assigned in a 2:1 ratio to intravenous remdesivir (200 mg on day 1 followed by 100 mg on days 2–10 in single daily infusions) or the same volume of placebo infusions for 10 days. Patients were permitted concomitant use of lopinavir–ritonavir, interferons, and corticosteroids. The primary endpoint was time to clinical improvement up to day 28, defined as the time (in days) from randomisation to the point of a decline of two levels on a six-point ordinal scale of clinical status (from 1=discharged

## C2 × Reference 1

Claim ID: `claim:caaa603f3a075608f0fae1717da2464a64389be0e360522a3563f8d1b6d155c8`

Reference ID: `reference:manuscript:420a8ea6573ba22c5f4852e0ee08722b09ebcc351081def1ee53665770cd3d1f:grobid-0.9.1-body-prose-v1:0`

ACTT-1 is a recent large clinical trial.

Status: completed / VERIFIED

Original adjudicator: SUPPORTS / 0.86; domain validated: SUPPORTED / 0.86

The evidence identifies ACTT-1 as a phase 3, randomized, double-blind, placebo-controlled trial ('a series of phase 3, randomized, double-blind, placebo-controlled trials') and documents a large, multicenter international operation with '60 trial sites and 13 subsites' in ten countries and substantial recorded events ('482 recoveries' and '81 deaths'), which reasonably supports 'large clinical trial.' 'Recent' is a time-relative term resolved against the manuscript's reference point and the 2020 cited source year; no chunk supplies a contrary chronology. The claim is a faithful, minimal descriptor rather than an expansion of findings, so SUPPORTS is appropriate. Note that the supporting excerpts establish scale indirectly (site count and event counts) rather than by an explicit total enrollment figure, which tempers confidence slightly but does not undermine the characterization.

Warnings: ["ORIGINAL_CITATION_VERSION_UNCONFIRMED"]

### evidence:d2d98683fdf835ecd2a2de5e42cef6084516801c902f646a028399ab03e491eb

Section: Design; PaperQA score: 9; Source: source:126a2d33afafb4cc04617e9aa26a2d0d1781478eaf5ba58c012d45fa615a08ee

Enrollment for ACTT-1 began on February 21, 2020, and ended on April 19, 2020. There were 60 trial sites and 13 subsites in the United States (45 sites), Denmark (8), the United Kingdom (5), Greece (4), Germany (3), Korea (2), Mexico (2), Spain (2), Japan (1), and Singapore (1). Eligible patients were randomly assigned in a 1:1 ratio to receive either remdesivir or placebo. Randomization was stratified by study site and disease severity at enrollment. Patients were considered to have severe disease if they required mechanical ventilation, if they required supplemental oxygen, if the oxygen saturation as measured by pulse oximetry (Sp
o
2
) was 94% or lower while they were breathing ambient air, or if they had tachypnea (respiratory rate ≥24 breaths per minute). Remdesivir was administered intravenously as a 200-mg loading dose on day 1, followed by a 100-mg maintenance dose administered daily on days 2 through 10 or until hospital discharge or death. A matching placebo was administered

### evidence:4f20d40c2ae635fcc43edb074df86e550ea23bea79171d15129144ad9f33c018

Section: Conclusions; PaperQA score: 7; Source: source:126a2d33afafb4cc04617e9aa26a2d0d1781478eaf5ba58c012d45fa615a08ee

its ability to inhibit SARS-CoV-2 in vitro.
9
In addition, in nonhuman primate studies, remdesivir initiated 12 hours after inoculation with MERS-CoV
10
,
11
reduced lung virus levels and lung damage.

To evaluate the clinical efficacy and safety of putative investigational therapeutic agents among hospitalized adults with laboratory-confirmed Covid-19, we designed an adaptive platform trial to rapidly conduct a series of phase 3, randomized, double-blind, placebo-controlled trials. Here, we describe the first stage of the Adaptive Covid-19 Treatment Trial (ACTT-1), in which we evaluated treatment with remdesivir as compared with placebo. The results presented here represent an update to a preliminary report after complete follow-up.

### evidence:3224b2027631b1121f59bcc68b9c2ef35f43f4de014eacc1643dcdf0f1b0ea47

Section: Discussion; PaperQA score: 6; Source: source:126a2d33afafb4cc04617e9aa26a2d0d1781478eaf5ba58c012d45fa615a08ee

The primary outcome of the current trial was changed early in the trial, from a comparison of the eight-category ordinal scale scores on day 15 to a comparison of time to recovery up to day 29. Little was known about the natural clinical course of Covid-19 when the trial was designed in February 2020. Emerging data suggested that Covid-19 had a more protracted course than was previously known, which aroused concern that a difference in outcome after day 15 would have been missed by a single assessment at day 15. The amendment was proposed on March 22, 2020, by trial statisticians who were unaware of treatment assignment and had no knowledge of outcome data; when this change was proposed 72 patients had been enrolled. Although changes in the primary outcome are not common in trials for diseases that are well understood, it is recognized that in some trials, such as those involving poorly understood diseases, circumstances may require a change in the way an outcome is assessed or may nec

### evidence:c9056846403c395cfc2ae75c8b7730438c36d4045d46b6442f70735d9afd3edf

Section: Statistical Analysis; PaperQA score: 6; Source: source:126a2d33afafb4cc04617e9aa26a2d0d1781478eaf5ba58c012d45fa615a08ee

On April 27, 2020, the data and safety monitoring board reviewed efficacy results. Although this review was originally planned as an interim analysis, because of the rapid pace of enrollment, the review occurred after completion of enrollment while follow-up was still ongoing. At the time of the data and safety monitoring board report, which was based on data cutoff date of April 22, 2020, a total of 482 recoveries (exceeding the estimated number of recoveries needed for the trial) and 81 deaths had been entered in the database. At that time, the data and safety monitoring board recommended that the preliminary primary analysis report and mortality data from the closed safety report be provided to trial team members from the National Institute of Allergy and Infectious Diseases (NIAID). These results were subsequently made public. The treating physician could request to be made aware of the treatment assignment of patients who had not completed day 29 if clinically indicated (e.g., bec

### evidence:e3cf6e1267e3276f1d5035412766f2cb0463757f66ba4c99d82935fe37fa584b

Section: Discussion; PaperQA score: 6; Source: source:126a2d33afafb4cc04617e9aa26a2d0d1781478eaf5ba58c012d45fa615a08ee

reative solutions to overcome these challenges. Throughout the trial, we were able to enroll a diverse population, similar to the population that was being infected with SARS-CoV-2 during that period.

Given the preliminary results about remdesivir, the Food and Drug Administration issued an Emergency Use Authorization on May 1, 2020 (modified on August 28, 2020), to permit the use of remdesivir for treatment in adults and children hospitalized with suspected or laboratory-confirmed Covid-19. Remdesivir has also received full or conditional approval in several other countries since that time. However, given high mortality despite the use of remdesivir, it is clear that treatment with an antiviral drug alone is not likely to be sufficient for all patients. Current strategies are evaluating remdesivir in combination with modifiers of the immune response (e.g., the Janus kinase [JAK] inhibitor baricitinib in ACTT-2, and interferon beta-1a in ACTT-3). A variety of therapeutic approaches including novel antivirals, modifiers of the immune response or other intrinsic pathways, and combination approaches are needed to continue to improve outcomes in patients with Covid-19.

## C3 × Reference 5

Claim ID: `claim:1abebd4a94d5888d2e2cec1480e9d2150568eb81c0410f85d541da0cd71f7f87`

Reference ID: `reference:manuscript:420a8ea6573ba22c5f4852e0ee08722b09ebcc351081def1ee53665770cd3d1f:grobid-0.9.1-body-prose-v1:4`

Key secondary endpoints discussed in the trial protocol included the durations of hospitalization, supplemental oxygen, and mechanical ventilation.

Status: blocked_source / SOURCE_NOT_FOUND

Original adjudicator: NOT RUN / —; domain validated: NONE / —

No scientific verdict.

Warnings: []

## C4 × Reference 1

Claim ID: `claim:e9f2ede5e0df61d67e79f166152fcaf6064745cb9058707788ec3f4e795966ee`

Reference ID: `reference:manuscript:420a8ea6573ba22c5f4852e0ee08722b09ebcc351081def1ee53665770cd3d1f:grobid-0.9.1-body-prose-v1:0`

The cumulative recovery rate curves are in Fig. 2A of the original paper.

Status: completed / VERIFIED

Original adjudicator: SUPPORTS / 0.96; domain validated: SUPPORTED / 0.816

The Figure 2 caption chunk explicitly describes 'Kaplan–Meier Estimates of Cumulative Recoveries' and assigns cumulative recovery estimates in the overall population to Panel A. The claim is limited to the location of those curves in Fig. 2A, which the caption directly confirms. This is a faithful paraphrase and no evidence in the supplied chunks contradicts it.

Warnings: ["ORIGINAL_CITATION_VERSION_UNCONFIRMED"]

### evidence:adff9bfb10a985e3ea4dc4f0a40a79cf1f2ff0e810551951a9dba659e9a1e30e

Section: Figure 2. Kaplan–Meier Estimates of Cumulative Recoveries.; PaperQA score: 9; Source: source:126a2d33afafb4cc04617e9aa26a2d0d1781478eaf5ba58c012d45fa615a08ee

Cumulative recovery estimates are shown in the overall population (Panel A), in patients with a baseline score of 4 on the ordinal scale (not receiving oxygen; Panel B), in those with a baseline score of 5 (receiving oxygen; Panel C), in those with a baseline score of 6 (receiving high-flow oxygen or noninvasive mechanical ventilation; Panel D), and in those with a baseline score of 7 (receiving mechanical ventilation or extracorporeal membrane oxygenation [ECMO]; Panel E).

### evidence:3abb1e0ef3d8e6bc9451bfdddc5bd83f190c548c9801e199fd591baa2e1f9d4a

Section: Discussion; PaperQA score: 7; Source: source:126a2d33afafb4cc04617e9aa26a2d0d1781478eaf5ba58c012d45fa615a08ee

The benefit of remdesivir was most apparent in patients with a baseline ordinal score of 5 (receiving low-flow oxygen). Some of this difference may be due to the larger sample size in this category since confidence intervals for baseline ordinal scores of 4 (not receiving oxygen), 6 (receiving high-flow oxygen), and 7 (receiving ECMO or mechanical ventilation) were wide. However, the interaction tests suggest greater benefit (with respect to recovery and mortality) in lower ordinal score categories. This should not be interpreted as conclusively showing a lack of efficacy in higher ordinal score categories. The median recovery time for patients in category 7 could not be estimated, which suggests that the follow-up time may have been too short to evaluate that subgroup.

### evidence:f212146d697c9819dca13a0a5848a71f57915aaa52f55d8fc045fd807ef7e141

Section: Primary Outcome; PaperQA score: 7; Source: source:126a2d33afafb4cc04617e9aa26a2d0d1781478eaf5ba58c012d45fa615a08ee

Patients in the remdesivir group had a shorter time to recovery than patients in the placebo group (median, 10 days, as compared with 15 days; rate ratio for recovery, 1.29; 95% confidence interval [CI], 1.12 to 1.49; P<0.001) (
Figure 2
and
Table 2
). In the severe disease stratum (957 patients) the median time to recovery was 11 days, as compared with 18 days (rate ratio for recovery, 1.31; 95% CI, 1.12 to 1.52) (Table S4). The rate ratio for recovery was largest among patients with a baseline ordinal score of 5 (rate ratio for recovery, 1.45; 95% CI, 1.18 to 1.79); among patients with a baseline score of 4 and those with a baseline score of 6, the rate ratio estimates for recovery were 1.29 (95% CI, 0.91 to 1.83) and 1.09 (95% CI, 0.76 to 1.57), respectively. For those receiving mechanical ventilation or ECMO at enrollment (baseline ordinal score of 7), the rate ratio for recovery was 0.98 (95% CI, 0.70 to 1.36). Information on interactions of treatment with baseline ordinal score a

### evidence:a6b4109ef1a816a445748310172d4c673290b9213e1ab4bcee9c39578d2b2069

Section: Primary Outcome; PaperQA score: 5; Source: source:126a2d33afafb4cc04617e9aa26a2d0d1781478eaf5ba58c012d45fa615a08ee

r the onset of symptoms had a rate ratio for recovery of 1.20 (95% CI, 0.94 to 1.52) (
Figure 3
). The benefit of remdesivir was larger when given earlier in the illness, though the benefit persisted in most analyses of duration of symptoms (Table S6). Sensitivity analyses in which data were censored at earliest reported use of glucocorticoids or hydroxychloroquine still showed efficacy of remdesivir (9.0 days to recovery with remdesivir vs. 14.0 days to recovery with placebo; rate ratio, 1.28; 95% CI, 1.09 to 1.50, and 10.0 vs. 16.0 days to recovery; rate ratio, 1.32; 95% CI, 1.11 to 1.58, respectively) (Table S8).

### evidence:1e9af80f3fbac22bb2b6202e483af0ce514c66c6bc5a935454e9ce369b141cb8

Section: Statistical Analysis; PaperQA score: 4; Source: source:126a2d33afafb4cc04617e9aa26a2d0d1781478eaf5ba58c012d45fa615a08ee

The primary analysis was a stratified log-rank test of time to recovery with remdesivir as compared with placebo, with stratification by disease severity (the actual severity at baseline). (See the
Supplementary Appendix
for more information about the planned statistical analysis.) For time-to-recovery and time-to-improvement analyses, data for patients who did not recover and data for patients who died were censored at day 29.

## C4 × Reference 6

Claim ID: `claim:e9f2ede5e0df61d67e79f166152fcaf6064745cb9058707788ec3f4e795966ee`

Reference ID: `reference:manuscript:420a8ea6573ba22c5f4852e0ee08722b09ebcc351081def1ee53665770cd3d1f:grobid-0.9.1-body-prose-v1:5`

The cumulative recovery rate curves are in Fig. 2A of the original paper.

Status: completed / VERIFIED

Original adjudicator: INSUFFICIENT / 0.8; domain validated: INSUFFICIENT / 0

The sole evidence chunk (evidence:82a67bb40be83642c2bb6e0a242171ed7b15b3991b11c791a2d9fc72b5b9f98c) describes a general algorithm for reconstructing KM data by digitizing coordinates from published survival curves: 'The KM curves are in effect pictorial representations of these data. We use digital software to read in the coordinates of the KM curves from the published graph.' This establishes only generic methodology; it does not identify any figure in the original paper, does not mention 'Fig. 2A,' and does not mention cumulative recovery rate curves. The claim concerns a figure-level fact about a different document, and no supplied chunk describes that document's figure contents or layout. Absence of a matching statement is a retrieval/coverage limitation and may not be promoted to support, contradiction, or fabrication. The manuscript context's Fig. 2A reference is attributional context, not independent source evidence.

Warnings: ["ORIGINAL_CITATION_VERSION_UNCONFIRMED"]

### evidence:82a67bb40be83642c2bb6e0a242171ed7b15b3991b11c791a2d9fc72b5b9f98c

Section: Background; PaperQA score: 7; Source: source:02da6bc32553a03b80e38407750926262897ce3508abf50743b6e1b2f5e8dc38

text at a relatively small number of follow-up times in order to approximate aggregate or life-table data, and they did not use all of the information reported to help identify the censoring pattern.

In this paper, we develop an algorithm that attempts to reproduce the sufficient statistics in detail, by reconstructing the Kaplan-Meier data on which the survival curves are based. The KM curves are in effect pictorial representations of these data. We use digital software to read in the coordinates of the KM curves from the published graph and we use the information on numbers at risk, often published at four or five time points under the x-axis of the KM graph, and total number of events, where available, to reconstruct the Kaplan-Meier data for each arm. A key feature of our approach is the use of iterative numerical methods to solve the inverted KM equations, which is necessary to obtain consistent results and make the best use of the information available.

## C5 × Reference 1

Claim ID: `claim:026502f3f6dc97e5ba227491d3111ba235c480b9ebc0b06287b04e4637380ea0`

Reference ID: `reference:manuscript:420a8ea6573ba22c5f4852e0ee08722b09ebcc351081def1ee53665770cd3d1f:grobid-0.9.1-body-prose-v1:0`

The survival curves are in Supplementary Fig. S3 of the original paper.

Status: completed / VERIFIED

Original adjudicator: INSUFFICIENT / 0.75; domain validated: INSUFFICIENT / 0.50765625

The evidence confirms the cited trial reported Kaplan–Meier mortality/survival analyses (chunk a2fddba9: 'Kaplan–Meier estimates of mortality by day 15 were 6.7% in the remdesivir group and 11.9% in the placebo group'), so survival curves plausibly exist in the paper. However, no supplied chunk states where those curves appear. The only supplied figure description is Figure 2, described as 'Kaplan–Meier Estimates of Cumulative Recoveries' with Panels A–E (chunk adff9bfb), which concerns recovery, not survival/mortality, and does not exclude a separate supplementary survival figure. Because the claim is purely about figure location and no chunk addresses supplementary figure numbering or 'Supplementary Fig. S3,' the evidence cannot settle the assertion either way. This is not a contradiction (Figure 2 being the recovery figure is compatible with a separate supplementary survival figure) and not fabrication (retrieval silence does not show the figure is invented).

Warnings: ["Adjudicator returned INSUFFICIENT despite multiple strong supporting evidence items.","Suggested correction removed because verdict is INSUFFICIENT.","ORIGINAL_CITATION_VERSION_UNCONFIRMED"]

### evidence:a2fddba9dbc0c9c34d7e909506d3977dfb15d725c5dd9f0abba81be71f06c857

Section: Mortality; PaperQA score: 8; Source: source:126a2d33afafb4cc04617e9aa26a2d0d1781478eaf5ba58c012d45fa615a08ee

Kaplan–Meier estimates of mortality by day 15 were 6.7% in the remdesivir group and 11.9% in the placebo group (hazard ratio, 0.55; 95% CI, 0.36 to 0.83); the estimates by day 29 were 11.4% and 15.2% in two groups, respectively (hazard ratio, 0.73; 95% CI, 0.52 to 1.03). The between-group differences in mortality varied considerably according to baseline severity (
Table 2
), with the largest difference seen among patients with a baseline ordinal score of 5 (hazard ratio, 0.30; 95% CI, 0.14 to 0.64). Information on interactions of treatment with baseline ordinal score with respect to mortality is provided in Table S11.

### evidence:fc28d386d25dda59a3f8dcade2d8bea75009ed2d2ef7ee2f51bd466bf9e6144c

Section: Table 2. Outcomes Overall and According to Score on the Ordinal Scale in the Intention-to-Treat Population. * .; PaperQA score: 4; Source: source:126a2d33afafb4cc04617e9aa26a2d0d1781478eaf5ba58c012d45fa615a08ee

P values and confidence intervals have not been adjusted for multiple comparisons. NE denotes not possible to estimate.

Recovery rate ratios and hazard ratios were calculated from the stratified Cox model; the P value for this ratio was calculated with the stratified log-rank test (overall model stratified by actual disease severity). Recovery rate ratios greater than 1 indicate a benefit with remdesivir; hazard ratios less than 1 indicate a benefit with remdesivir.

Mortality over the first 14 days includes data from all patients who were still alive through 14 days postenrollment, with data censored on day 15, as if 14 days was the maximum follow-up time. Mortality over the entire study period uses the totality of the study data and censors data from patients who completed follow-up alive at 28 days postenrollment.

### evidence:c2afe729a4462df1f0c17da08429db55c7f925c5bbe389bfacfe12894fe6838c

Section: Outcomes; PaperQA score: 3; Source: source:126a2d33afafb4cc04617e9aa26a2d0d1781478eaf5ba58c012d45fa615a08ee

and duration of new oxygen use, of noninvasive ventilation or high-flow oxygen, and of invasive ventilation or ECMO; number of days of hospitalization up to day 29; and mortality at 14 and 28 days after enrollment. Secondary safety outcome measures included grade 3 and 4 adverse events and serious adverse events that occurred during the trial, discontinuation or temporary suspension of infusions, and changes in assessed laboratory values over time.

### evidence:1e9af80f3fbac22bb2b6202e483af0ce514c66c6bc5a935454e9ce369b141cb8

Section: Statistical Analysis; PaperQA score: 2; Source: source:126a2d33afafb4cc04617e9aa26a2d0d1781478eaf5ba58c012d45fa615a08ee

The primary analysis was a stratified log-rank test of time to recovery with remdesivir as compared with placebo, with stratification by disease severity (the actual severity at baseline). (See the
Supplementary Appendix
for more information about the planned statistical analysis.) For time-to-recovery and time-to-improvement analyses, data for patients who did not recover and data for patients who died were censored at day 29.

### evidence:adff9bfb10a985e3ea4dc4f0a40a79cf1f2ff0e810551951a9dba659e9a1e30e

Section: Figure 2. Kaplan–Meier Estimates of Cumulative Recoveries.; PaperQA score: 2; Source: source:126a2d33afafb4cc04617e9aa26a2d0d1781478eaf5ba58c012d45fa615a08ee

Cumulative recovery estimates are shown in the overall population (Panel A), in patients with a baseline score of 4 on the ordinal scale (not receiving oxygen; Panel B), in those with a baseline score of 5 (receiving oxygen; Panel C), in those with a baseline score of 6 (receiving high-flow oxygen or noninvasive mechanical ventilation; Panel D), and in those with a baseline score of 7 (receiving mechanical ventilation or extracorporeal membrane oxygenation [ECMO]; Panel E).

## C5 × Reference 6

Claim ID: `claim:026502f3f6dc97e5ba227491d3111ba235c480b9ebc0b06287b04e4637380ea0`

Reference ID: `reference:manuscript:420a8ea6573ba22c5f4852e0ee08722b09ebcc351081def1ee53665770cd3d1f:grobid-0.9.1-body-prose-v1:5`

The survival curves are in Supplementary Fig. S3 of the original paper.

Status: completed / VERIFIED

Original adjudicator: INSUFFICIENT / 0.85; domain validated: INSUFFICIENT / 0

The only evidence chunk is a reference list. It makes no assertion about figures, supplementary files, or the placement of survival curves, so it cannot confirm the claim that the survival curves are in Supplementary Fig. S3 of the original paper. Conversely, nothing in it supplies a conflicting location or otherwise contradicts the claim, so CONTRADICTS is unwarranted, and there is no compelling evidence of fabrication. The relevant portions of the source (figure captions or results text) are simply unavailable, which is a retrieval gap rather than proof the claim is false.

Warnings: ["ORIGINAL_CITATION_VERSION_UNCONFIRMED"]

### evidence:bc4854a28edf03f031be0579a91a97d4d344fe9ea0c26de02d8f32178b84236b

Section: References; PaperQA score: 2; Source: source:02da6bc32553a03b80e38407750926262897ce3508abf50743b6e1b2f5e8dc38

ple time. Biometrics. 1994;50:989–1002. doi: 10.2307/2533438.

Arends L, Hunink M, Stijnen T. Meta-analysis of summary survival curve. Statistics in medicine. 2008;27:4381–4396. doi: 10.1002/sim.3311.

Fiocco M, Putter H, van Houwelingen JC. Meta-analysis of pairs of survival curves under heterogeneity: a Poisson correlated gamma-frailty approach. Statistics in medicine. 2009;28:3782–3797. doi: 10.1002/sim.3752.

Parmar MKB, Torri V, Stewart L. Extracting summary statistics to perform meta-analyses of the published literature for survival endpoints. Statistics in medicine. 1998;17:2815–2834. doi: 10.1002/(SICI)1097-0258(19981230)17:24<2815::AID-SIM110>3.0.CO;2-8.

Ouwens MJNM, Philips Z, Jansen JP. Network meta-analysis of parametric survival curves. Research Synthesis Methods. 2010;1(3-4):258–271. doi: 10.1002/jrsm.25.

Jansen JP. Network meta-analysis of survival data with fractional polynomials. BMC Medical Research Methodology. 2011;11:61. doi: 10.1186/1471-2288-11-61.

## C6 × Reference 7

Claim ID: `claim:05d796fdfd426dcfee033a3f23b15a6a8d335e2d0de3b756225b02c6178baf41`

Reference ID: `reference:manuscript:420a8ea6573ba22c5f4852e0ee08722b09ebcc351081def1ee53665770cd3d1f:grobid-0.9.1-body-prose-v1:6`

The mean times, up to day 28, that patients spent in hospital receiving attentive care are shown in panels 2B and C.

Status: completed / NO_RELEVANT_EVIDENCE

Original adjudicator: NOT RUN / —; domain validated: INSUFFICIENT / 0

Evidence retrieval did not produce usable chunks for agent analysis.

Warnings: ["ORIGINAL_CITATION_VERSION_UNCONFIRMED"]

## C6 × Reference 8

Claim ID: `claim:05d796fdfd426dcfee033a3f23b15a6a8d335e2d0de3b756225b02c6178baf41`

Reference ID: `reference:manuscript:420a8ea6573ba22c5f4852e0ee08722b09ebcc351081def1ee53665770cd3d1f:grobid-0.9.1-body-prose-v1:7`

The mean times, up to day 28, that patients spent in hospital receiving attentive care are shown in panels 2B and C.

Status: completed / NO_RELEVANT_EVIDENCE

Original adjudicator: NOT RUN / —; domain validated: INSUFFICIENT / 0

Evidence retrieval did not produce usable chunks for agent analysis.

Warnings: ["ORIGINAL_CITATION_VERSION_UNCONFIRMED"]

## C6 × Reference 9

Claim ID: `claim:05d796fdfd426dcfee033a3f23b15a6a8d335e2d0de3b756225b02c6178baf41`

Reference ID: `reference:manuscript:420a8ea6573ba22c5f4852e0ee08722b09ebcc351081def1ee53665770cd3d1f:grobid-0.9.1-body-prose-v1:8`

The mean times, up to day 28, that patients spent in hospital receiving attentive care are shown in panels 2B and C.

Status: failed / DOI_MISSING

Original adjudicator: NOT RUN / —; domain validated: NONE / —

No scientific verdict.

Warnings: []

## C6 × Reference 10

Claim ID: `claim:05d796fdfd426dcfee033a3f23b15a6a8d335e2d0de3b756225b02c6178baf41`

Reference ID: `reference:manuscript:420a8ea6573ba22c5f4852e0ee08722b09ebcc351081def1ee53665770cd3d1f:grobid-0.9.1-body-prose-v1:9`

The mean times, up to day 28, that patients spent in hospital receiving attentive care are shown in panels 2B and C.

Status: blocked_source / SOURCE_REQUIRED_FULL_TEXT_UNAVAILABLE

Original adjudicator: NOT RUN / —; domain validated: NONE / —

No scientific verdict.

Warnings: []

## C8 × Reference 14

Claim ID: `claim:faca882ed3d7e85b06c1407a5442a617b0aa2ddfb87dcbcd2a5e1b90e0c9ffc7`

Reference ID: `reference:manuscript:420a8ea6573ba22c5f4852e0ee08722b09ebcc351081def1ee53665770cd3d1f:grobid-0.9.1-body-prose-v1:13`

The areas below the cumulative incidence curves in Figures 3B and 3C represent the mean event-free survival times up to day 28.

Status: completed / VERIFIED

Original adjudicator: CONTRADICTS / 0.95; domain validated: CONTRADICTED / 0.95

The source Figure 3 caption states: "B and C. Mean time in recovery, as the area under the cumulative incidence curve, across the 28 days of study follow-up." The text similarly states: "the area under the cumulative recovery curve is the average postrecovery time that study patients spent." These statements refer to the same entity as the claim: the areas under the cumulative incidence curves in Figures 3B and 3C for the ACTT-1 recovery analysis over 28 days. The source defines that area as mean time in recovery / average postrecovery time, not mean event-free survival time. Calling it event-free survival changes the outcome being summarized and is therefore substantively incompatible with the source, rather than an ordinary paraphrase.

Warnings: ["ORIGINAL_CITATION_VERSION_UNCONFIRMED"]

### evidence:480f710af1316540ac783d6186ed2e0c981396033926e6fd1c672a458107b3ca

Section: Summarizing Cumulative Recovery Curves: Alternatives to the Hazard Ratio for Time to Recovery; PaperQA score: 8; Source: source:008395bd012f1d200bd27731d3a0c6c8ab572a331c970dae25390f770deb9a62

fference is 4.7 percentage points (CI, −2.8 to 11.6 percentage points;
= 0.20). Thus, whether remdesivir was superior to placebo with respect to the cumulative recovery rate on day 28 is inconclusive.

An alternative summary of the cumulative recovery rate over time is the area under the cumulative incidence curve up to 28 days. Intuitively, the larger the area, the better the therapy. In
B
and
C
, we present these areas of 11.9 and 14.1 days for the remdesivir and placebo groups, respectively. The clinical interpretation is informative; the area under the cumulative recovery curve is the average postrecovery time that study patients spent, as displayed for hypothetical patients on the right-hand side of
Figure 1
. Therefore, across the 28 days of follow-up, patients receiving remdesivir spent 14.1 postrecovery days, on average, whereas patients receiving placebo spent only 11.9 days. The difference of 2.2 days (CI, 0.89 to 3.52 days;
< 0.001) favors remdesivir. Zhao and
colleagues (
12
) recently presented a similarly intuitive summary measure for cardiovascular clinical studies in the presence of competing risks.

### evidence:df1244871b3f4ed45f28e762129313751423a9268308c89bc3c2435ac1aa715f

Section: Figure 3. Cumulative incidence curves ( A ) and mean postrecovery times ( B and C ).; PaperQA score: 8; Source: source:008395bd012f1d200bd27731d3a0c6c8ab572a331c970dae25390f770deb9a62

A.
Cumulative incidence curves from ACTT-1 (Adaptive COVID-19 Treatment Trial) for the proportion of patients recovered, treating death as a competing risk and depicting days corresponding to the median recovery.
B and C.
Mean time in recovery, as the area under the cumulative incidence curve, across the 28 days of study follow-up.

### evidence:80eb3e57d978c84370f1d67302b5fb0f634f1a9387341286604d582e6c8129a1

Section: Survival Analysis via the Mean Survival Time Across the Study Period; PaperQA score: 6; Source: source:008395bd012f1d200bd27731d3a0c6c8ab572a331c970dae25390f770deb9a62

For the standard overall survival time in these examples, competing risks are not present and the standard Kaplan–Meier curves are appropriate. For overall survival, as for recovery, the higher the curve, the better the treatment. Thus, the area under the overall survival curve also provides a summary of treatment efficacy. In fact, the area under the Kaplan–Meier curve across a specific time window is the restricted mean survival time, which has been discussed extensively in the literature (
15–18
). For ACTT-1, by using reconstructed data from Figure S3 in the original paper (
5
), the 28-day restricted mean survival times were 26.1 days for remdesivir and 25.3 days for placebo (
Supplement
Figure 3 in Part G of the
Supplement
, available at Annals.org). The difference was 0.76 days (CI, −0.09 to 1.61 days;
= 0.079). That is, across the 28 days of follow-up, patients receiving remdesivir survived 0.76 days longer, on average, than those receiving placebo. These summaries are much eas

### evidence:f38cd95c94970a1979e0ecc5aee0f7d639c9089326698a5ce764f1f1412b256f

Section: Discussion; PaperQA score: 5; Source: source:008395bd012f1d200bd27731d3a0c6c8ab572a331c970dae25390f770deb9a62

ce in the areas under the cumulative incidence curves. We then summarize the overall treatment effect via the average of the aforementioned stratum-specific differences, weighted by the stratum sizes.

All our analyses were performed in the R statistical computing environment (3.6.2; R Foundation for Statistical Computing) (
20
). Kaplan–Meier curves were constructed by using the
survival
package (
21
), cumulative incidence curves were estimated by using the
cmprsk
package (
22
), and survival differences and restricted mean survival time analyses were conducted by using the
surv2sampleComp
package (
23
). We have made software for analyzing the area under the cumulative incidence curve publicly available (
24
).

### evidence:cc321a7e06c5e8b5ec104843350b164e6d29a46019bda3978f15943b83bfde46

Section: Summarizing Cumulative Recovery Curves: Alternatives to the Hazard Ratio for Time to Recovery; PaperQA score: 4; Source: source:008395bd012f1d200bd27731d3a0c6c8ab572a331c970dae25390f770deb9a62

ecision of a median estimate is often quite low, as reflected by the wide CI. Moreover, if the recovery rate on day 28 was less than 50%, then the median recovery time cannot be empirically estimated.

The cumulative recovery rate on day 28 is also a reasonable summary if the time to recovery during the study is not of primary interest. Estimates for these rates correspond to the vertical distance from the
x
-axis to the cumulative incidence curves in
A
. In the present case, these were 74% and 70%, respectively, for remdesivir and placebo. The difference is 4.7 percentage points (CI, −2.8 to 11.6 percentage points;
= 0.20). Thus, whether remdesivir was superior to placebo with respect to the cumulative recovery rate on day 28 is inconclusive.

## C9 × Reference 14

Claim ID: `claim:6c55b88d6b20d456980517a2cf5037b852e711684dd0b3cdc2b3b4e41dd996bb`

Reference ID: `reference:manuscript:420a8ea6573ba22c5f4852e0ee08722b09ebcc351081def1ee53665770cd3d1f:grobid-0.9.1-body-prose-v1:13`

Remdesivir numerically prolonged patients' survival.

Status: completed / VERIFIED

Original adjudicator: SUPPORTS / 0.96; domain validated: SUPPORTED / 0.96

The core assertion is that remdesivir showed a numerical survival advantage, not that the advantage was statistically significant. The source states that patients receiving remdesivir survived 0.76 days longer on average across 28 days than those receiving placebo, and it reports higher day-28 survival rates for remdesivir (88% vs 85%). The CI and p-value indicate lack of statistical significance, which is compatible with the claim's explicit 'numerically' qualifier.

Warnings: ["ORIGINAL_CITATION_VERSION_UNCONFIRMED"]

### evidence:d027b0dd715d064813ed47dbcdaa4a221843cf6c6d530ca580ba54d222a2bcd8

Section: Survival Analysis via the Mean Survival Time Across the Study Period; PaperQA score: 10; Source: source:008395bd012f1d200bd27731d3a0c6c8ab572a331c970dae25390f770deb9a62

−0.09 to 1.61 days;
= 0.079). That is, across the 28 days of follow-up, patients receiving remdesivir survived 0.76 days longer, on average, than those receiving placebo. These summaries are much easier to contextualize than the corresponding hazard ratio of 0.70 (CI, 0.47 to 1.04;
= 0.07). The overall survival rates on day 28 were 88% and 85% for remdesivir and placebo, with a difference of 3.1 percentage points (CI, −2.2 to 8.3 percentage points;
= 0.25). For mortality, the 28-day rate difference is probably a better summary than either the hazard ratio or the mean survival time difference, considering the short follow-up.

### evidence:513fa42a3688c5bf1fb464bda18ea7c2ccaca0a622893370bfcfc845e1054dbb

Section: Example 1: ACTT-1; PaperQA score: 8; Source: source:008395bd012f1d200bd27731d3a0c6c8ab572a331c970dae25390f770deb9a62

In ACTT-1 (
5
), 538 patients were assigned to remdesivir and 521 to placebo. Respectively, 334 and 273 patients recovered and 132 and 169 observations were censored, as in case 3. By day 15, 33 and 55 patients in the remdesivir and placebo groups, respectively, had died. Figure S3 of the original paper depicts the overall survival curves through day 29.

### evidence:823b75e7674d62550902712a0cc7a7851edcf105bd872cb4493b7459d020775d

Section: Figure 1. Possible patterns for time to recovery for ACTT-1 (Adaptive COVID-19 Treatment Trial) and the study by Li and colleagues ( 7 ).; PaperQA score: 5; Source: source:008395bd012f1d200bd27731d3a0c6c8ab572a331c970dae25390f770deb9a62

In the remdesivir and convalescent plasma studies, the death of a patient before the end of the study prevents us from observing recovery or improvement. Because death is a negative outcome, whereas recovery or improvement is positive, the standard technique of defining a composite end point, such as the time to recovery or improvement or the time to death, is not applicable. Moreover, because the potential death and recovery times of each patient are probably correlated, standard survival analysis methods that treat death as independent censoring are not appropriate.

### evidence:aa84e8298f1a3a252a2a840377de13462baaade703894970127bb02052a10eee

Section: Example 1; PaperQA score: 5; Source: source:008395bd012f1d200bd27731d3a0c6c8ab572a331c970dae25390f770deb9a62

ACTT-1 (Adaptive COVID-19 Treatment Trial) is an ongoing double-blind, randomized, placebo-controlled trial of remdesivir versus placebo in adults hospitalized with COVID-19 who have evidence of lower respiratory tract involvement (
5
). Patient health was closely monitored across 28 days of follow-up and classified on an 8-point ordinal scale (Part B of the
Supplement
, available at Annals.org), with category 1 being the most favorable outcome (discharge from hospital with no limitation of activities) and category 8 being death. The primary end point was time to recovery, defined as the first time during the 28 days of follow-up the patient attained category 1, 2, or 3.

### evidence:51efa91b6a62cf77327cb0e908d3115cb02c1610fae4f00089c95b0ff7ba04ca

Section: Summarizing Cumulative Recovery Curves: Alternatives to the Hazard Ratio for Time to Recovery; PaperQA score: 4; Source: source:008395bd012f1d200bd27731d3a0c6c8ab572a331c970dae25390f770deb9a62

89 to 3.52 days;
< 0.001) favors remdesivir. Zhao and
colleagues (
12
) recently presented a similarly intuitive summary measure for cardiovascular clinical studies in the presence of competing risks.

For the study by Li and colleagues (
7
), the hazard ratio for time to improvement was 1.40 (CI, 0.79 to 2.49;
= 0.26). Across the 28 days of follow-up, the area under the cumulative incidence curve (
Supplement
Figure 1) was 7.4 days for convalescent plasma and 5.2 days for standard care, for a difference of 2.2 days (CI, −0.96 to 5.2 days;
= 0.17). That is, across the 28 days of follow-up, patients receiving convalescent plasma spent 2.2 more postimprovement days, on average, than patients receiving standard care.

## C10 × Reference 15

Claim ID: `claim:38901c49f7e3a7e988dfd2dbe1d49c19b0980ede49794e08277ed7f40dfd77d1`

Reference ID: `reference:manuscript:420a8ea6573ba22c5f4852e0ee08722b09ebcc351081def1ee53665770cd3d1f:grobid-0.9.1-body-prose-v1:14`

The complexity extends to other cases in which initiation of the event of interest does not necessarily start when the patient enters the study.

Status: completed / VERIFIED

Original adjudicator: SUPPORTS / 0.84; domain validated: SUPPORTED / 0.63

Chunk f6f4ee35 describes response profiles in which response 'occurred at Month 2' or 'occurred at Month 3,' i.e., after study entry. Chunk e7118be4 explains that DOR and censoring time are measured from the initial response, 'which is itself an outcome of treatment,' producing dependent censoring and analytic complexity. This matches the claim that there are cases where initiation of the event of interest does not necessarily start when the patient enters the study and that such cases add complexity. The evidence supports the claim as a reasonable methodological paraphrase rather than an overstatement.

Warnings: ["ORIGINAL_CITATION_VERSION_UNCONFIRMED"]

### evidence:e7118be4b93158267ea9894072830eb5fc10cd51895fec9b9f65b56b079a26c8

Section: THE DURATION OF RESPONSE (DOR); PaperQA score: 9; Source: source:f918653eb0428002b9495428af1213380ab7bc5bd24f21cabc456ae54665b3cf

s only, the standard approach of constructing Kaplan-Meier curves and reporting the median duration of response, without formal statistical inference, does not allow us to draw conclusions about treatment efficacy. For this case, the Kaplan-Meier curves are not valid due to the presence of dependent censoring. As an example of such censoring, consider case 3 in
Figure 1
, whose response began at Month 2 and was censored at Month 4. Since both, the duration of response and the censoring time are measured from the initial response at Month 2, which is itself an outcome of treatment, the duration of response and censoring time are potentially dependent. In general, the Kaplan-Meier curve is biased for estimating the distribution of the duration of response under dependent censoring (
14
).

### evidence:f6f4ee359609c57a286134c681a70558b9728def4a0c09ab093c926cfb818239

Section: INTRODUCTION; PaperQA score: 8; Source: source:f918653eb0428002b9495428af1213380ab7bc5bd24f21cabc456ae54665b3cf

o respond rapidly and remain in response for a prolonged period, the duration of response has become an important and clinically meaningful outcome measure, especially in oncology studies (
6
10
11
).

A response may not be observable if disease progression or death or a censoring event occurs first.
Figure 1
presents six possible case profiles for a response outcome. For the first case, response occurred at Month 2 and continued until Month 8, when progression or death occurred. For the second case, response occurred at Month 3 and progression or death occurred at Month 5. For the third case, response occurred at Month 2, but censoring occurred at Month 4. For the fourth case, censoring occurred at Month 3, before response. For the fifth case, progression or death occurred at Month 5, before response. For the last case, progression or death occurred at Month 10, again before response.

### evidence:2a6f98c9dd52108909ec69ed9d5087ef0f119290a9f2de1377362173a79782f5

Section: Figure 3.; PaperQA score: 7; Source: source:f918653eb0428002b9495428af1213380ab7bc5bd24f21cabc456ae54665b3cf

Using Duration of Response (DOR) Data from the JAVELIN Renal-101 Study to illustrate potentially biased comparisons via standard Kaplan-Meier procedure among
A
. Responders only (subject to patients’ selection bias); and
B.
All Patients (subject to bias due to dependent censoring)

### evidence:c0876af2069674b861c8e2a119f0dc58bebabc3c686ad979f998d78e1a7aa376

Section: CURRENT RESPONSE RATE OR PROBABILITY-OF-BEING-IN-RESPONSE (PBIR); PaperQA score: 6; Source: source:f918653eb0428002b9495428af1213380ab7bc5bd24f21cabc456ae54665b3cf

The current response rate or the probability-of-being-in-response (PBIR) is the proportion of patients who have achieved response and remain in response at present. This measure estimates the current rate rather than the cumulative response rate at a specific time. In
Figure 1
, case 2 is a responder at Month 3, but not at Month 6. Case 3 is a responder from Month 2 until censoring event at Month 4. For further illustration, consider a study in which the cumulative response rate at Month 6 is 40%, but the current response rate is only 20%. This result indicates that many early responders have not sustained their responses. Although the current response rate has been used outside of oncology studies, inference procedures utilized in practice might not be appropriate, especially in the presence of censoring. In this article, we extend the discussion from the probability-of-being-in-response (PBIR) at a fixed time point to the entire study period.

### evidence:8a060d7f39503264757d99c9c63b933753b835ad299785bb685e96c09b17546d

Section: DURATION OF RESPONSE (DOR); PaperQA score: 3; Source: source:f918653eb0428002b9495428af1213380ab7bc5bd24f21cabc456ae54665b3cf

al response rates among all-comers. However, this adjustment does not remedy the bias arising from dependent censoring (
14
). A simple alternative method for estimating the mean duration of response while incorporating data from both responders and non-responders is presented next.

