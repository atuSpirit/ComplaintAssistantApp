import pandas as pd
import numpy as np
import pickle
import matplotlib.pyplot as plt
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, f1_score, roc_auc_score, roc_curve
from sklearn.model_selection import train_test_split
from scipy.sparse import hstack


from ComplaintsAnalysis.SMOTEOverSampling import smote_over_sampling
from ComplaintsAnalysis.TextPreprocess import tf_idf_vectorize, dump_tf_idf_model
from ComplaintsAnalysis.Utilities import scale_features


def merge_narrative_processed_and_sentiment_metrics(narrative_preprocessed_file, complaints_with_sentiment):
    """Load the feature and label csv file and merge them according to complaint ID"""
    complaints = pd.read_csv(complaints_with_sentiment)
    complaints = complaints[["Complaint ID", "Timely response?", "Product", "corpus_score_sum", "corpus_score_ave", "negative_ratio",
             "most_negative_score", "word_num", "sentence_num", "num_of_question_mark", "num_of_exclaimation_mark",
             "company_response"]]

    # One hot coding the column "company_response", store the column name of dummy columns
    # to be used when predicting
    old_column_num = len(complaints.columns)
    complaints = pd.get_dummies(complaints, columns=["company_response"])
    new_column_names = []
    for i in np.arange(old_column_num - 1, len(complaints.columns)):
        new_column_names.append(complaints.columns[i])

    # Save the new column names to a file
    column_name_file = "trained_models/company_corresponse_variable_names.csv"
    with open(column_name_file, "w") as fobj:
        fobj.write(",".join(new_column_names))

    narrative_processed = pd.read_csv(narrative_preprocessed_file)

    complaints_features = pd.merge(complaints.reset_index(drop=True), narrative_processed.reset_index(drop=True),
                               how='inner', on=['Complaint ID', 'Complaint ID'])

    print("Loading {} complaints ".format(complaints_features.shape))

    return complaints_features


def model_evaluate(model, X_test, y_test, is_rf=False, tag="all"):
    """Evaluate model by accuracy, confusion matrix and f1 score"""
    pred_model = model.predict(X_test)
    confusion = confusion_matrix(y_test, pred_model)
    print("Confusion matrix:\n{}".format(confusion))
    print("f1 score: {:.2f}".format(f1_score(y_test, pred_model)))

    # Computing the AUC score as the criteria for the imbalance data
    if is_rf == True:
        model_auc = roc_auc_score(y_test, model.predict_proba(X_test)[:, 1])
        # plot the roc curve
        fpr, tpr, thresholds = roc_curve(y_test, model.predict_proba(X_test)[:, 1])
    else:
        model_auc = roc_auc_score(y_test, model.decision_function(X_test))
        # plot the roc curve
        fpr, tpr, thresholds = roc_curve(y_test, model.decision_function(X_test))

    plt.plot(fpr, tpr, label='ROC curve of {} (AUC = {:,.2f})'.format(tag, model_auc))

    # Add the chance line
    plt.plot([0, 1], [0, 1], linestyle='--', lw=2, color='black',
             label='Chance', alpha=.8)
    #plt.savefig(roc_fig)

    print("AUC for model is: {:.3f}".format(model_auc))


def feature_engineer(X_train, X_test, tag="all"):
    """
    For complaints_features, generate sentiment_metrics and vectorize
    processed_narratives and join them as a feature for classifier.
    :param X_train: X_train data
    :param X_test: X_test data
    :param tag: The tag as suffix to save the tf-idf vectorizer
    :return: X_train and X_test are tf-idf transformed and merge with sentiment metrics
    """
    X_train_sentiment_metric = X_train.loc[:, "corpus_score_sum":"company_response_Untimely response"]

    # print(complaints_features[["processed_narrative"]].shape)
    print("Tf-idf vectorizing...")
    tf_idf_vectorizer, X_train_narratives_vectorized, max_feature_num = tf_idf_vectorize(
        X_train["processed_narrative"], 1)

    print("Saving Tf-idf model")
    save_dir = "trained_models"
    dump_tf_idf_model(tf_idf_vectorizer, max_feature_num, save_dir, tag)

    X_train = hstack((X_train_narratives_vectorized, np.array(X_train_sentiment_metric)))

    # X_test
    X_test_sentiment_metric = X_test.loc[:, "corpus_score_sum":"company_response_Untimely response"]
    X_test_narratives_vectorized = tf_idf_vectorizer.transform(X_test["processed_narrative"])
    X_test = hstack((X_test_narratives_vectorized, np.array(X_test_sentiment_metric)))

    return X_train, X_test


def logistic_regression_model(X_train, X_test, y_train, y_test, tag, save_dir):
    lgreg = LogisticRegression(C=1, solver="lbfgs", max_iter=2000)
    lgreg.fit(X_train, y_train)
    is_rf = False
    model_evaluate(lgreg, X_test, y_test, is_rf, tag)

    # save the model
    pickle.dump(lgreg, open(save_dir + "/lgreg.{}.pickle".format(tag), "wb"))


def gradient_boosting_model(X_train, X_test, y_train, y_test, tag, save_dir):
    gbrt = GradientBoostingClassifier(random_state=0)
    gbrt.fit(X_train, y_train)
    is_rf = False
    model_evaluate(gbrt, X_test, y_test, is_rf, tag)

    # save the model
    pickle.dump(gbrt, open(save_dir + "/gbrt.{}.pickle".format(tag), "wb"))


def build_classifier(complaints_features, classifier_model, tag, save_dir):
    """
    Build a classifier using classifier_model to classify complaints_features data
    :param complaints_features: Complaint data with processed narrative and sentiment
     metrics
    :param classifier_model: the function to apply given classifier
    :param tag: product category as a suffix to save the model and figs
    :return:
    """

    #X = complaints_features.loc[:, "corpus_score_sum":"company_response_Untimely response"]
    X = complaints_features
    y = [0 if x == "No" else 1 for x in complaints_features["Consumer disputed?"]]

    X_trainval, X_test, y_trainval, y_test = train_test_split(X, y, random_state=42)

    # scale
    X_trainval, X_test = scale_features(X_trainval, X_test)

    # Feature engineering by vectorizing and generate sentiment metrics
    X_trainval, X_test = feature_engineer(X_trainval, X_test, tag)

    # Oversampling using SMOTE
    X_trainval_res, y_trainval_res = smote_over_sampling(X_trainval, y_trainval)

    classifier_model(X_trainval_res, X_test, y_trainval_res, y_test, tag, save_dir)


def main():
    # Load the feature and label csv file, join them according to complaint ID
    complaints_with_sentiment = "data/complaints_with_sentiment_metric.csv"
    narrative_preprocessed_file = "data/narrative_preprocessed.csv"
    complaints_features = merge_narrative_processed_and_sentiment_metrics(narrative_preprocessed_file,
                                                                          complaints_with_sentiment)
    model_save_dir = "trained_models"

    # The classifier model to run
    classifier_model = logistic_regression_model
    model_tag = "lgrg"
    # classifier_model = gradient_boosting_model
    # model_tag = "gbm"

    # Build a classifier for all category together
    tag = "all"
    build_classifier(complaints_features, classifier_model, tag, model_save_dir)

    # For each product category, build the classifier
    products = list(complaints_features["Product"].unique())
    for product in products:
        print("Building classifier for ", product)
        complaints_features_one_category = complaints_features[complaints_features["Product"] == product]
        print("There are {} complaints in category {}".format(len(complaints_features_one_category),
                                                              product))
        # print(complaints_features_one_category.head())

        # The tag used as suffix of roc curve and model save
        tag = "_".join(product.split(" "))

        plt.title("ROC curve for escalate classifier for " + tag)
        plt.xlabel("False Positive Rate")
        plt.ylabel("True Positive Rate")
        plt.legend(loc="lower right")

        build_classifier(complaints_features_one_category, classifier_model, tag, model_save_dir)

        roc_fig = "figs/roc_escalation_classifier_" + model_tag + "_" + tag + ".png"
        plt.savefig(roc_fig)

#main()