import pandas as pd
import numpy as np
import re
import matplotlib.pyplot as plt

from scipy.sparse import hstack

from ComplaintsAnalysis.SentimentMetricGenerator import generate_sentiment_metric
from ComplaintsAnalysis.TextPreprocess import pre_process_narrative
from ComplaintsAnalysis.Utilities import load_models, get_response_types, PRODUCT_LABELS


class Predictor:
    def __init__(self):
        print("Loading models...")
        model_dir = "ComplaintsAnalysis/trained_models"
        clf_product_file = model_dir + "/" + "product_classifier_lgreg.sav"
        clf_escalation_file = model_dir + "/" + "lgreg.all.joblib"
        tf_idf_vectorizer_file = model_dir + "/" + "tfidf_vectorizer_max50000.all.joblib"
        scaler_file = model_dir + "/" + "scaler.joblib"
        stop_words_file = model_dir + "/" + "STOP_WORDs.txt"
        self.clf_product, self.clf_escalation, self.tf_idf_vectorizer, self.scaler, self.stop_words = load_models(clf_product_file,
                                                                             clf_escalation_file,
                                                                             tf_idf_vectorizer_file,
                                                                             scaler_file,
                                                                             stop_words_file)

    def predict(self, narrative):
        """
        Given a narrative,
        1. predict the product category
        2. predict the escalation probability based on different response type
        3. draw a bar chart of the probabilites
        4. return response type with lowest escalation probability
        :param narrative:
        :param clf_product: pre-trained product classifier
        :param clf_escalation: pre-trained escalation classifier
        :return: product category, bar chart, the suggest response type
        """
        sentiment_metric = generate_sentiment_metric([narrative])
        sentiment_metric.loc[:, ["word_num", "sentence_num"]] = self.scaler.transform(
            sentiment_metric.loc[:, ["word_num", "sentence_num"]])

        # Transfer narrative to feature vector be used by classifier
        preprocessed_narrative = pre_process_narrative(narrative, self.stop_words)
        narrative = " ".join(preprocessed_narrative)

        narrative_vectorized = self.tf_idf_vectorizer.transform([narrative])

        # print("tf_idf sum: {}".format(np.sum(narrative_vectorized.max(axis=0).toarray().ravel())))

        # Predict the product type of this complaint
        product_type = self.predict_product_type(narrative_vectorized)
        # print("The complaint is about " + product_type)

        # Predict the probabilities of escalation when adopting
        escalation_prob_fig, response, escalation_probas_according_response = self.predict_escalation(narrative_vectorized,
                                                                                                      sentiment_metric)

        response = response.split("_")[-1]
        response = re.sub(r"Closed with ", "", response).capitalize()

        return product_type, escalation_prob_fig, response, escalation_probas_according_response

    def predict_product_type(self, narrative_vectorized):
        # product_type_list = clf_product.predict(narrative_vectorized)[0]
        product_type_prob = self.clf_product.predict_proba(narrative_vectorized)[0]
        # print(product_type_prob)
        index_product_most_prob = np.argmax(product_type_prob)
        # print(index_product_most_prob)
        product_type = PRODUCT_LABELS[index_product_most_prob]

        return product_type

    def predict_escalation(self, narrative_vectorized, sentiment_metric):
        # Predict probability of dispute according to all different responses
        response_types = get_response_types()
        predict_probability_list = []

        # Add company_response dummy variable in
        column_name_base = "company_response_"
        new_column_names = [column_name_base + x for x in response_types]

        # Predict for each type of response, whether the narrative will end in a dispute
        for response in response_types:
            # One hot code for X_to_predict
            for new_column_name in new_column_names:
                sentiment_metric[new_column_name] = 0
            column_name = column_name_base + response
            sentiment_metric[column_name] = 1

            X_to_predict = hstack((narrative_vectorized, np.array(sentiment_metric)))
            result = self.clf_escalation.predict(X_to_predict)

            """
            if result:
                print("If respond with {}, there will have escalation!".format(response))
            else:
                print("If respond with {}, there is no escalation!".format(response))
            """

            predict_probability = self.clf_escalation.predict_proba(X_to_predict)[0][1]
            # print(predict_probability)
            predict_probability_list.append(predict_probability)

        # Draw bar chart of escalation probability under different responses
        escalation_prob_fig = "static/escalation_prob.png"

        data = pd.DataFrame()
        data["Company Response"] = response_types
        data["Probability of Escalation"] = predict_probability_list

        escalation_prob_thresh = 0.5
        plt.figure(figsize=(5, 5))
        barlist = plt.bar(response_types, predict_probability_list, alpha=0.8)
        for i in np.arange(len(predict_probability_list)):
            if predict_probability_list[i] >= escalation_prob_thresh:
                barlist[i].set_color('r')

        plt.ylabel('Probability of Escalation', fontsize=12)
        plt.xlabel('Company Response Types', fontsize=12)
        plt.xticks(rotation=45)
        plt.yticks(np.arange(0, 1.1, step=0.1))
        plt.gcf().subplots_adjust(bottom=0.35)
        plt.savefig(escalation_prob_fig, bbox_inches='tight')

        # Suggest the response type not to be the one with minimum probability to escalate,
        # because money-relief will always be the one with lowest probabilty. However, money
        # relief need cost. Current criteria is to pick the one with max prob but lower than
        # a given threshold
        suggested_prob_thresh = escalation_prob_thresh - 0.15
        min_prob = min(predict_probability_list)
        suggested_index = predict_probability_list.index(min(predict_probability_list))
        for index in np.arange(len(predict_probability_list)):
            if (predict_probability_list[index] < suggested_prob_thresh) & \
                    (predict_probability_list[index] > min_prob):
                min_prob = predict_probability_list[index]
                suggested_index = index

        suggested_response = response_types[suggested_index]

        return escalation_prob_fig, suggested_response, predict_probability_list

    def test(self):
        print("Predicting...")
        narrative = "I have a complaint regarding the overdraft fees that were billed to my checking account. I have a complaint regarding the overdraft fees that were billed to mychecking account. I was charged XXXX overcharge fees for XXXX withdrawals in which I had funds in the account. I contact your office and spoke with a representativewho credited me with XXXX of the fees back. However, the XXXX fee was never credited. I just do n't understand how I can billed for an overdraft fee when the fundswere in my accounts. I contacted the office of the president for Flagstar Bank and my compliant was pushed aside. Flagstar has now filed a writ of garnishmentwith my employer."
        product_type, escalation_prob_fig, suggest_response = self.predict(narrative)
        print("The complaints is about " + product_type)
        print("Suggested response type is " + suggest_response)

