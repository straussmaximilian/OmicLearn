import pandas as pd
import streamlit as st
from utils.helper import get_svg_download_link, get_pdf_download_link
from utils.helper import make_recording_widget, load_data, transform_dataset, normalize_dataset
from utils.helper import select_features, plot_feature_importance, impute_nan, perform_cross_validation, plot_confusion_matrices
from utils.helper import perform_cohort_validation, plot_roc_curve_cv, plot_roc_curve_cohort, get_system_report
from PIL import Image
icon = Image.open('./utils/proto_learn.png')

# Checkpoint for XGBoost
xgboost_installed = False
try:
    from xgboost import XGBClassifier
    import xgboost
    xgboost_installed = True
except ModuleNotFoundError:
    st.error('Xgboost not installed. To use xgboost install using `conda install py-xgboost`')

# Get Version
with open("./utils/__version__.py") as version_file:
    version = version_file.read().strip()

# Set color palette
blue_color = '#0068c9'
red_color = '#f63366'
gray_color ='#f3f4f7'

# Functions / Element Creations
def main_components():
    # External CSS
    main_external_css = """
        <style>
            #MainMenu, .reportview-container .main footer {display: none;}
            .download_link {color: #f63366 !important; text-decoration: none !important; z-index: 99999 !important; 
                            cursor:pointer !important; margin: 15px 0px; border: 1px solid #f63366; 
                            text-align:center; padding: 8px !important; width: 200px;}
            .download_link:hover {background: #f63366 !important; color: #FFF !important;}
        </style>
    """
    st.markdown(main_external_css, unsafe_allow_html=True)
    st.sidebar.image(icon, use_column_width=True, caption="Proto Learn v" + version,)

    widget_values = {}
    n_missing = 0
    class_0, class_1 = None, None

    # Sidebar widgets
    button_ = make_recording_widget(st.sidebar.button, widget_values)
    slider_ = make_recording_widget(st.sidebar.slider, widget_values)
    multiselect_ = make_recording_widget(st.sidebar.multiselect, widget_values)
    number_input_ = make_recording_widget(st.sidebar.number_input, widget_values)
    selectbox_ = make_recording_widget(st.sidebar.selectbox, widget_values)
    multiselect = make_recording_widget(st.multiselect, widget_values)

    return widget_values, n_missing, class_0, class_1, button_, slider_, multiselect_, number_input_, selectbox_, multiselect

def main_text_and_data_upload():
    st.title("Proto Learn — Clinical Proteomics Machine Learning Tool")
    st.info(""" 
        * Upload your excel / csv file here. Maximum size is 200 Mb.
        * Each row corresponds to a sample, each column to a feature
        * Protein names should be uppercase
        * Additional features should be marked with a leading '_'
    """)
    st.sidebar.title("Options")
    st.subheader("Dataset")
    file_buffer = st.file_uploader("Upload your dataset below", type=["csv", "xlsx"])
    sample_file = st.selectbox("Or select sample file here:", ["None", "Sample"])
    df = load_data(file_buffer)
    return sample_file, df

def checkpoint_for_data_upload(sample_file, df, class_0, class_1, n_missing, multiselect):
    if (sample_file != 'None') and (len(df) > 0):
        st.warning("Please, either choose a sample file or set it as `None` to work on your file")
        df = pd.DataFrame()
    elif sample_file != 'None':
        st.text("Here is the sample dataset:")
        df = pd.read_excel('data/'+ sample_file + '.xlsx')
        st.write(df)
    elif len(df) > 0:
        st.text("Here is your dataset:")
        st.write(df)
    else:
        st.error('No dataset uploaded.')

    n_missing = df.isnull().sum().sum()

    if len(df) > 0:
        if n_missing > 0:
            st.warning('Found {} missing values. Use missing value imputation or xgboost classifier.'.format(n_missing))

        # Distinguish the proteins from others
        proteins = [_ for _ in df.columns.to_list() if _[0] != '_']
        not_proteins = [_ for _ in df.columns.to_list() if _[0] == '_']

        st.subheader("Subset")
        st.text('Create a subset based on values in the selected column')
        subset_column = st.selectbox("Select subset column", ['None']+not_proteins)

        if subset_column != 'None':
            subset_options = df[subset_column].value_counts().index.tolist()
            subset_class = multiselect("Select values to keep", subset_options, default=subset_options)
            df_sub = df[df[subset_column].isin(subset_class)].copy()
        else:
            df_sub = df.copy()

        st.subheader("Features")
        option = st.selectbox("Select target column", not_proteins)
        st.markdown("Unique elements in `{}` column.".format(option))
        unique_elements = df_sub[option].value_counts()
        st.write(unique_elements)
        unique_elements_lst = unique_elements.index.tolist()

        # Define classes
        st.subheader("Define classes".format(option))
        class_0 = multiselect("Class 0", unique_elements_lst, default=None)
        class_1 = multiselect("Class 1", [_ for _ in unique_elements_lst if _ not in class_0], default=None)
        remainder = [_ for _ in not_proteins if _ is not option]

        # Define `exclude_features` and `additional_features` as empty if the classes are not defined
        exclude_features, additional_features = "", ""
        if class_0 and class_1:
            st.subheader("Additional features")
            st.text("Select additional features. All non numerical values will be encoded (e.g. M/F -> 0,1)")
            additional_features = st.multiselect("Additional features for trainig", remainder, default=None)
            #Todo: Check if we need additional features
            st.subheader("Exclude proteins")
            exclude_features = st.multiselect("Select proteins that should be excluded", proteins, default=None)

        st.subheader("Cohort comparison")
        st.text('Select cohort column to train on one and predict on another')
        cohort_column = st.selectbox("Select cohort column", ['None']+not_proteins)

        return class_0, class_1, df, unique_elements_lst, cohort_column, exclude_features, remainder, proteins, not_proteins, option, df_sub, additional_features, n_missing, subset_column

def generate_sidebar_elements(slider_, selectbox_, number_input_, n_missing, additional_features):
    random_state = slider_("RandomState", min_value = 0, max_value = 99, value=23)
    st.sidebar.markdown('## [Preprocessing](https://github.com/OmicEra/proto_learn/wiki/METHODS-%7C-1.-Preprocessing)')
    normalizations = ['None', 'StandardScaler', 'MinMaxScaler', 'MaxAbsScaler', 'RobustScaler', 'PowerTransformer', 'QuantileTransformer(Gaussian)','QuantileTransformer(uniform)','Normalizer']
    normalization = selectbox_("Normalization", normalizations)

    if n_missing > 0:
        st.sidebar.markdown('## [Missing value imputation](https://github.com/OmicEra/proto_learn/wiki/METHODS-%7C-5.-Imputation-of-missing-values)')
        missing_values = ['Zero', 'Mean', 'Median', 'IterativeImputer', 'KNNImputer', 'None']
        missing_value = selectbox_("Missing value imputation", missing_values)
    else:
        missing_value = 'None'

    st.sidebar.markdown('## [Feature selection](https://github.com/OmicEra/proto_learn/wiki/METHODS-%7C-2.-Feature-selection)')
    feature_methods = ['DecisionTree', 'k-best (mutual_info)','k-best (f_classif)', 'Manual']
    feature_method = selectbox_("Feature selection method", feature_methods)

    if feature_method != 'Manual':
        max_features = number_input_('Maximum number of features', value = 20, min_value = 1, max_value = 2000)

    st.sidebar.markdown('## [Classification](https://github.com/OmicEra/proto_learn/wiki/METHODS-%7C-3.-Classification#3-classification)')

    if xgboost_installed:
        classifiers = ['AdaBoost','LogisticRegression','RandomForest','XGBoost','DecisionTree']
    else:
        classifiers = ['AdaBoost','LogisticRegression','RandomForest','DecisionTree']

    if n_missing > 0:
        if missing_value == 'None':
            classifiers = ['XGBoost']

    classifier = selectbox_("Classifier", classifiers)

    # Define n_estimators as 0 if classifier not Adaboost
    n_estimators = 0

    if classifier == 'AdaBoost':
        n_estimators = number_input_('number of estimators', value = 100, min_value = 1, max_value = 2000)

    st.sidebar.markdown('## [Cross Validation](https://github.com/OmicEra/proto_learn/wiki/METHODS-%7C-4.-Cross-Validation)')
    cv_splits = number_input_('CV Splits', min_value = 2, max_value = 10, value=5)
    cv_repeats = number_input_('CV Repeats', min_value = 1, max_value = 50, value=10)

    features_selected = False

    # Define manual_features and features as empty if method is not Manual
    manual_features, features = "", ""

    if feature_method == 'Manual':
        manual_features = st.multiselect("Manually select proteins", proteins, default=None)
        features = manual_features +  additional_features
        
    return random_state, normalization, missing_value, feature_method, max_features, classifiers, n_estimators, cv_splits, cv_repeats, features_selected, classifier, manual_features, features

def feature_selection(df, option, class_0, class_1, df_sub, additional_features, proteins, normalization, feature_method, max_features, random_state):
    st.subheader("Feature selection")
    class_names = [df[option].value_counts().index[0], df_sub[option].value_counts().index[1]]
    st.markdown("Using the following identifiers: Class 0 `{}`, Class 1 `{}`".format(class_0, class_1))
    subset = df_sub[df_sub[option].isin(class_0) | df_sub[option].isin(class_1)].copy()

    st.write(subset[option].value_counts())
    y = subset[option].isin(class_0) #is class 0 will be 1!
    X = transform_dataset(subset, additional_features, proteins)
    X = normalize_dataset(X, normalization)

    if feature_method == 'Manual':
        pass
    else:
        features, feature_importance, p_values = select_features(feature_method, X, y, max_features, random_state)
        p, feature_df = plot_feature_importance(features, feature_importance, p_values)
        st.plotly_chart(p, use_container_width=True)
        if p:
            get_pdf_download_link(p, 'feature_importance.pdf')
        # st.dataframe(feature_df)
    
    return class_names, subset, X, y, features

def all_plotting_and_results(X, y, subset, cohort_column, classifier, random_state, cv_splits, cv_repeats, class_0, class_1):
    # Cross-Validation                
    st.markdown("Running Cross-Validation")
    _cv_results, roc_curve_results, split_results = perform_cross_validation(X, y, classifier, cv_splits, cv_repeats, random_state, st.progress(0))
    st.header('Cross-Validation')
    st.subheader('Receiver operating characteristic')
    p = plot_roc_curve_cv(roc_curve_results)
    st.plotly_chart(p)
    if p:
        get_pdf_download_link(p, 'roc_curve.pdf')

    st.subheader('Confusion matrix')
    #st.text('Performed on the last CV split')
    names = ['CV_split {}'.format(_+1) for _ in range(len(split_results))]
    names.insert(0, 'Sum of all splits')
    layout, p, fig  = plot_confusion_matrices(class_0, class_1, split_results, names)
    st.bokeh_chart(layout)
    # st.plotly_chart(fig)
    # get_pdf_download_link(p, 'cm_cohorts.pdf')

    st.subheader('Run Results for `{}`'.format(classifier))
    summary = pd.DataFrame(_cv_results).describe()
    st.write(pd.DataFrame(summary))

    # Set these values as empty if cohort_column is `None`
    _cohort_results, roc_curve_results_cohort, cohort_results, cohort_combos = "", "", "", ""

    if cohort_column != 'None':
        st.header('Cohort comparison')
        st.subheader('Receiver operating characteristic',)
        _cohort_results, roc_curve_results_cohort, cohort_results, cohort_combos = perform_cohort_validation(X, y, subset, cohort_column, classifier, random_state, st.progress(0))

        p = plot_roc_curve_cohort(roc_curve_results_cohort, cohort_combos)
        st.plotly_chart(p)
        if p:
            get_pdf_download_link(p, 'roc_curve_cohort.pdf')

        st.subheader('Confusion matrix')
        names = ['Train on {}, Test on {}'.format(_[0], _[1]) for _ in cohort_combos]
        names.insert(0, 'Sum of cohort comparisons')
        layout, p, fig = plot_confusion_matrices(class_0, class_1, cohort_results, names)
        # st.plotly_chart(fig)
        # get_pdf_download_link(p, 'cm.pdf')
        st.bokeh_chart(layout)

        st.subheader('Run Results for `{}`'.format(classifier))
        summary = pd.DataFrame(_cohort_results).describe()
        st.write(pd.DataFrame(summary))

    return summary, _cohort_results, roc_curve_results_cohort, cohort_results, cohort_combos

def generate_text(normalization, proteins, feature_method, classifier, cohort_column, cv_repeats, cv_splits, class_0, class_1, summary, _cohort_results, cohort_combos):
    st.write("## Summary")
    report = get_system_report()
    text ="```"
    
    # Packages
    text += "Machine learning was done in Python ({python_version}). Protein tables were imported via the pandas package ({pandas_version}). The machine learning pipeline was employed using the scikit-learn package ({sklearn_version}). ".format(**report)

    # Normalization
    if normalization == 'None':
        text += 'After importing, no further normalization was performed. '
    else:
        text += 'After importing, features were normalized using a {} approach. '.format(normalization)

    # Feature
    if feature_method == 'Manual':
        text += 'A total of {} proteins were manually selected. '.format(len(proteins))
    else:
        text += 'Proteins were selected using a {} strategy. '.format(feature_method)

    # Classifier
    if classifier is not 'XGBoost':
        text += 'For classification, we used a {}-Classifier. '.format(classifier)
    else:
        text += 'For classification, we used a {}-Classifier ({}). '.format(classifier, xgboost.__version__ )

    # Cross-Validation
    text += 'When using a repeated (n_repeats={}), stratified cross-validation (n_splits={}) approach to classify {} vs. {}, we achieved a receiver operating characteristic (ROC) with an average AUC (area under the curve) of {:.2f} ({:.2f} std). '.format(cv_repeats, cv_splits, ''.join(class_0), ''.join(class_1), summary.loc['mean']['roc_auc'], summary.loc['std']['roc_auc'])

    if cohort_column is not 'None':
        text += 'When training on one cohort and predicting on another to classify {} vs. {}, we achieved the following AUCs: '.format(''.join(class_0), ''.join(class_1))
        for i, cohort_combo in enumerate(cohort_combos):
            text+= '{:.2f} when training on {} and predicting on {}. '.format(pd.DataFrame(_cohort_results).iloc[i]['roc_auc'], cohort_combo[0], cohort_combo[1])
    text +="```"
    st.markdown(text)


# Saving session info
@st.cache(allow_output_mutation=True)
def get_sessions():
    return [], {}

def save_sessions(widget_values, user_name):
    session_no, session_dict = get_sessions()
    session_no.append(len(session_no) + 1)
    # st.write(session_no)
    session_dict[session_no[-1]] = widget_values
    # st.write(session_dict)
    sessions_df = pd.DataFrame(session_dict)
    sessions_df = sessions_df.T
    sessions_df = sessions_df.drop(sessions_df[sessions_df["user"] != user_name].index).reset_index(drop=True)
    # sessions_df = sessions_df[sessions_df["user"] == user_name]
    st.write("## Session History")
    st.dataframe(sessions_df)

# Main Function
def ProtoLearn_Main():
    # Main components
    widget_values, n_missing, class_0, class_1, button_, slider_, multiselect_, number_input_, selectbox_, multiselect = main_components()

    # Welcome text and Data uploading 
    sample_file, df = main_text_and_data_upload()

    # Checkpoint for whether data uploaded/selected
    class_0, class_1, df, unique_elements_lst, cohort_column, exclude_features, \
    remainder, proteins, not_proteins, option, df_sub, additional_features, \
    n_missing, subset_column = checkpoint_for_data_upload(sample_file, df, class_0, class_1, n_missing, multiselect)

    # Sidebar widgets
    random_state, normalization, missing_value, feature_method, max_features, classifiers, \
    n_estimators, cv_splits, cv_repeats, features_selected, classifier, manual_features, features = generate_sidebar_elements(slider_, selectbox_, number_input_, n_missing, additional_features)

    # Analysis Part
    if (df is not None) and (class_0 and class_1) and (st.button('Run Analysis', key='run')):
        proteins = [_ for _ in proteins if _ not in exclude_features]

        # Feature Selection
        class_names, subset, X, y, features = feature_selection(df, option, class_0, class_1, df_sub, additional_features, proteins, normalization, feature_method, max_features, random_state)
        st.markdown('Using classifier `{}`.'.format(classifier))
        st.markdown('Using features `{}`.'.format(features))
        # result = cross_validate(model, X=_X, y=_y, groups=_y, cv=RepeatedStratifiedKFold(n_splits=cv_splits, n_repeats=cv_repeats, random_state=0) , scoring=metrics, n_jobs=-1)

        # Define X vector and impute the NaN values
        X = X[features]
        X = impute_nan(X, missing_value, random_state)

        # Plotting and Get the results
        summary, _cohort_results, roc_curve_results_cohort, \
        cohort_results, cohort_combos = all_plotting_and_results(X, y, subset, cohort_column, classifier, random_state, cv_splits, cv_repeats, class_0, class_1)

        # Generate summary text
        generate_text(normalization, proteins, feature_method, classifier, cohort_column, cv_repeats, cv_splits, class_0, class_1, summary, _cohort_results, cohort_combos)
        
        # Session
        import getpass, SessionState, random
        user_name = str(random.randint(0,10000)) + "protoLearn"
        session_state = SessionState.get(user_name=user_name)
        widget_values["roc_auc_mean"] = summary.loc['mean']['roc_auc']
        widget_values["roc_auc_std"] = summary.loc['std']['roc_auc']
        widget_values["user"] = session_state.user_name
        save_sessions(widget_values, session_state.user_name)

# Run the Proto Learn
if __name__ == '__main__':
    try:
        ProtoLearn_Main()
    except (ValueError, IndexError) as val_ind_error:
        st.error("There is a problem with values/parameters or dataset due to {}.".format(val_ind_error))
    except TypeError as e:
        # st.warning("TypeError exists in {}".format(e))
        pass
